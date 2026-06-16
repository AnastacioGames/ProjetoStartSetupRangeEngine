import Range
import json
import os
from collections import OrderedDict
import mathutils

# --- TRATAMENTO PARA A INTERFACE DO BLENDER ---
# Impede crashes quando a interface lê as teclas
try:
	from Range import events
except:
	class FakeEvents:
		def __getattr__(self, name): return 0
	events = FakeEvents()


class SaveManager(Range.types.KX_PythonComponent):
	_instance = None

	args = OrderedDict([
		("C_Icons", "DISK_DRIVE"),  # Ícone de disco para identificar fácil

		("C_Header /Arquivo/SETTINGS", True),
		("File Name", "savefile.json"),  # Nome do arquivo no disco
		("Profile File", "profile.json"), # Arquivo para salvar progresso global
		("Auto Load", False),  # Carregar assim que iniciar?
		("Debug Mode", True),

		("C_Header /Controles/VIEW3D", True),
		("Save Key", "K"),  # Tecla para salvar (ex: K, S, SPACE)
		("Load Key", "L"),  # Tecla para carregar (ex: L, R)
		
		("C_Header /Filtro/FILTER", True),
		("Save Only With Props", False),  # Salva apenas objetos que possuam propriedades

		("C_Header /Interface/SCENE", True),
		("UI Scene", "0_SCN_System"),  # Cena onde os popups serão criados
		("UI Spawner", "msg_status"),  # Objeto Empty que servirá de âncora
		("Save Popup", "Msg_Save"),    # Nome do objeto visual de Save
		("Load Popup", "Msg_Load"),    # Nome do objeto visual de Load
		("Popup Lifetime", 60),        # Tempo de vida do popup em frames
	])

	@staticmethod
	def get():
		return SaveManager._instance

	def awake(self, args):
		# Registra a instância no objeto para o BrainCore achar fácil depois
		# Ex: o BrainCore vai procurar por self.object["save_instance"]
		self.object["save_instance"] = self
		SaveManager._instance = self

		# Inicializa o container de dados vazio
		self.data = {}
		self.profile_data = {}

		# Variáveis de controle
		self.filename = args["File Name"]
		self.profile_filename = args.get("Profile File", "profile.json")
		self.debug = args["Debug Mode"]
		self.save_only_with_props = args.get("Save Only With Props", False)

		# Configurações de UI (agora expostas e controladas pelo painel)
		self.ui_scene_name = args.get("UI Scene", "0_SCN_System")
		self.ui_spawner = args.get("UI Spawner", "msg_status")
		self.save_popup = args.get("Save Popup", "Msg_Save")
		self.load_popup = args.get("Load Popup", "Msg_Load")
		self.popup_lifetime = args.get("Popup Lifetime", 60)

		# Busca o código da tecla na API da Range usando a string limpa ("K", "L")
		save_key_str = args.get("Save Key", "K").replace("KEY", "").upper() + "KEY"
		load_key_str = args.get("Load Key", "L").replace("KEY", "").upper() + "KEY"
		self.save_key = getattr(events, save_key_str, events.KKEY)
		self.load_key = getattr(events, load_key_str, events.LKEY)

		# Referência direta ao teclado
		self.keyboard = Range.logic.keyboard

	def start(self, args):
		# Se estiver marcado para carregar automático
		if args["Auto Load"]:
			self.load()
			
		# Carrega o perfil global automaticamente
		self.load_profile()

	def update(self):
		# --- CAIXA DE CORREIO (Ouvinte Global para Progresso) ---
		cmd_complete = Range.logic.globalDict.get("CompleteLevel")
		if cmd_complete:
			self.mark_level_completed(cmd_complete)
			del Range.logic.globalDict["CompleteLevel"]
			
		for sensor in self.object.sensors:
			if hasattr(sensor, "subjects") and sensor.positive:
				for subject, body in zip(sensor.subjects, sensor.bodies):
					if subject == "CompleteLevel" and body:
						self.mark_level_completed(body)

		if getattr(self, "_pending_load_data", False):
			core = self.object.get("core_instance")
			if core and not core.is_loading and core.active_scene_name == self.data.get("saved_level"):
				self._apply_scene_data()
				self._spawn_popup(self.load_popup)
				self._pending_load_data = False
				
				# Força o jogo a entrar em Pause logo após terminar de carregar (Loading)
				if not core.is_paused:
					core.toggle_pause()
			return

		# Puxa o status das teclas atuais do jogo normal
		save_input = self.keyboard.inputs[self.save_key]
		load_input = self.keyboard.inputs[self.load_key]

		# '.activated' verifica se a tecla acabou de ser apertada (Tap/Click)
		if getattr(save_input, "activated", False):
			if Range.logic.globalDict.get("GAME_STATE") in ["PLAYING", "PAUSED"]:
				self.save()
			
		if getattr(load_input, "activated", False):
			if Range.logic.globalDict.get("GAME_STATE") in ["PLAYING", "PAUSED"]:
				self.load()

	# --- MÉTODOS DE SERVIÇO (CHAMADOS PELO BRAINCORE) ---

	def _gather_scene_data(self):
		"""Coleta posição, rotação e propriedades dos objetos permitidos na cena"""
		scenes_data = {}
		for scene in Range.logic.getSceneList():
			# Ignora a cena de sistema
			if scene.name == "0_SCN_System":
				continue
				
			obj_dict = {}
			for obj in scene.objects:
				prop_names = obj.getPropertyNames()
				props = {}
				if prop_names:
					for p in prop_names:
						# Ignora propriedades visuais de UI (Header, Collapse, Icons)
						if not str(p).startswith("C_"):
							props[p] = obj[p]
							
				# Verifica se é Dinâmico/Character/Rigid, Empty ou Instância de Grupo
				is_dynamic = obj.mass > 0.0
				is_empty = len(obj.meshes) == 0
				is_group = hasattr(obj, "groupMembers") and obj.groupMembers is not None
				is_group_member = hasattr(obj, "groupObject") and obj.groupObject is not None
				
				has_valid_props = bool(props)
				is_valid_type = is_dynamic or is_empty or is_group or is_group_member
				
				# Aplica a regra escolhida no painel
				if self.save_only_with_props:
					if not has_valid_props:
						continue
				else:
					if not has_valid_props and not is_valid_type:
						continue
					
				# Captura Posição e Rotação usando Euler(Graus/Radiano) para facilitar a leitura no JSON
				pos = [obj.worldPosition.x, obj.worldPosition.y, obj.worldPosition.z]
				euler = obj.worldOrientation.to_euler()
				rot = [euler.x, euler.y, euler.z]
				
				if obj.name not in obj_dict:
					obj_dict[obj.name] = []
					
				obj_dict[obj.name].append({
					"position": pos,
					"rotation": rot,
					"properties": props
				})
			
			if obj_dict:
				scenes_data[scene.name] = obj_dict
		return scenes_data

	def _apply_scene_data(self):
		"""Aplica os dados salvos e recria objetos dinâmicos faltantes"""
		saved_scenes = self.data.get("scenes", {})
		for scene in Range.logic.getSceneList():
			if scene.name in saved_scenes:
				scene_data = saved_scenes[scene.name]
				
				# Mapeia objetos que já estão vivos na cena (agrupados por nome em listas)
				current_objects = {}
				for obj in scene.objects:
					if obj.name not in current_objects:
						current_objects[obj.name] = []
					current_objects[obj.name].append(obj)
				
				for obj_name, instances_data in scene_data.items():
					# Compatibilidade com saves antigos (onde era apenas um dicionário em vez de lista)
					if isinstance(instances_data, dict):
						instances_data = [instances_data]
						
					existing_instances = current_objects.get(obj_name, [])
					
					for i, obj_data in enumerate(instances_data):
						# 1. Se já existe um objeto na cena, usa ele. Se não, SPAWNA!
						if i < len(existing_instances):
							obj = existing_instances[i]
						else:
							obj_matrix = scene.objectsInactive.get(obj_name)
							if obj_matrix:
								anchor = scene.active_camera if scene.active_camera else scene.objects[0]
								obj = scene.addObject(obj_matrix, anchor)
							else:
								obj = None
								
						# 2. Aplica posição, rotação e propriedades
						if obj:
							if "position" in obj_data:
								obj.worldPosition = obj_data["position"]
							if "rotation" in obj_data:
								obj.worldOrientation = mathutils.Euler(obj_data["rotation"]).to_matrix()
							
							if "properties" in obj_data:
								for p_name, p_val in obj_data["properties"].items():
									if p_name in obj:
										obj[p_name] = p_val
										
					# 3. Limpeza! Se a cena recarregou com MAIS objetos desse tipo do que no save,
					# significa que o jogador destruiu alguns. Precisamos deletar os que sobraram!
					if len(existing_instances) > len(instances_data):
						for extra_obj in existing_instances[len(instances_data):]:
							extra_obj.endObject()

	def _spawn_popup(self, popup_name):
		"""Instancia um objeto de UI na cena de sistema"""
		spawner = None
		spawner_scene = None
		for scene in Range.logic.getSceneList():
			if scene.name == self.ui_scene_name:
				spawner = scene.objects.get(self.ui_spawner)
				spawner_scene = scene
				break
				
		obj_matrix = None
		for scene in Range.logic.getSceneList():
			obj_matrix = scene.objectsInactive.get(popup_name)
			if obj_matrix:
				break
				
		if spawner_scene and spawner and obj_matrix:
			spawner_scene.addObject(obj_matrix, spawner, self.popup_lifetime)

	def save(self):
		"""Salva o dicionário self.data no arquivo JSON"""
		core = self.object.get("core_instance")
		if core and core.active_scene_name in core.menu_scenes:
			return  # Nunca salva sobre um menu!

		# 1. Varredura automática das Cenas e Objetos
		self.data["scenes"] = self._gather_scene_data()
		
		# 2. Salva qual é a fase atual no BrainCore
		
		# Abre a tela de Pause automaticamente ao apertar Salvar
		if core and not core.is_paused:
			core.toggle_pause()
			
		if core and core.active_scene_name:
			self.data["saved_level"] = core.active_scene_name

		path = Range.logic.expandPath("//" + self.filename)

		# Garante que o diretório exista antes de salvar (previne crash se tiver subpastas)
		save_dir = os.path.dirname(path)
		if save_dir and not os.path.exists(save_dir):
			os.makedirs(save_dir)

		try:
			with open(path, 'w') as outfile:
				json.dump(self.data, outfile, indent=4)

			self._spawn_popup(self.save_popup)

		except Exception as e:
			print(f"[SaveManager] ERRO AO SALVAR: {e}")

	def load(self):
		"""Carrega do arquivo JSON para a memória (self.data)"""
		path = Range.logic.expandPath("//" + self.filename)

		if not os.path.exists(path):
			# Define valores padrão (vazio) caso não exista save
			self.data = {}
			return

		try:
			with open(path, 'r') as infile:
				self.data = json.load(infile)
				
			# Interação com o Core: Força o reload da fase (mesmo se for a atual) antes de injetar os dados
			saved_level = self.data.get("saved_level", "")
			core = self.object.get("core_instance")
			
			if core and saved_level:
				core.load_level(saved_level)
				self._pending_load_data = True
			else:
				self._apply_scene_data()
				self._spawn_popup(self.load_popup)
				
				# Pausa o jogo caso o load tenha sido feito instantaneamente (mesma fase)
				if core and not core.is_paused:
					core.toggle_pause()

		except Exception as e:
			print(f"[SaveManager] ARQUIVO CORROMPIDO: {e}")
			self.data = {}  # Zera para evitar crash

	# --- SISTEMA DE PERFIL (PROGRESSO GLOBAL) ---
	def save_profile(self):
		"""Salva dados que independem da fase (ex: fases concluidas)"""
		path = Range.logic.expandPath("//" + self.profile_filename)
		save_dir = os.path.dirname(path)
		if save_dir and not os.path.exists(save_dir):
			os.makedirs(save_dir)
		try:
			with open(path, 'w') as outfile:
				json.dump(self.profile_data, outfile, indent=4)
		except Exception as e:
			pass
			
	def load_profile(self):
		"""Carrega dados globais do jogador"""
		path = Range.logic.expandPath("//" + self.profile_filename)
		if not os.path.exists(path):
			self.profile_data = {"completed_levels": []}
			return
		try:
			with open(path, 'r') as infile:
				self.profile_data = json.load(infile)
		except:
			self.profile_data = {"completed_levels": []}
			
	def mark_level_completed(self, level_name):
		if "completed_levels" not in self.profile_data:
			self.profile_data["completed_levels"] = []
		if level_name not in self.profile_data["completed_levels"]:
			self.profile_data["completed_levels"].append(level_name)
			self.save_profile()

	# --- API PARA O JOGO ---

	def set_value(self, key, value):
		"""Define um valor na memória (não salva no disco ainda)"""
		self.data[key] = value

	def get_value(self, key, default=None):
		"""Recupera um valor da memória"""
		return self.data.get(key, default)
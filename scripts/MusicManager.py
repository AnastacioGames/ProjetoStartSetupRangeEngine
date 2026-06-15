import Range
import aud
import os
from collections import OrderedDict
from Range import logic

""" como usar
from scripts.MusicManager import MusicManager

def iniciar_corrida():
    # Música longa, com fade suave, lida do disco
    MusicManager.get().play("RACE_1", fade_time=3.0)    
"""


class MusicManager(Range.types.KX_PythonComponent):
	_instance = None

	args = OrderedDict([
		("C_Icons", "SOUND"),
		("C_Header /Audio/SETTINGS", True),
		("Music Volume", 0.5),
		("SFX Volume", 1.1),
		("Fade Time", 2.0),
		
		("C_Header /Interface/UI", True),
		("UI Scene", "0_SCN_Systen"),
		("UI Spawner", "msg_status"),
		("Music Popup", "Msg_Music"),  # Nome do objeto de UI que vai aparecer
		("Popup Lifetime", 200),        # Tempo que ele fica na tela
	])

	@staticmethod
	def get():
		return MusicManager._instance

	def awake(self, args):
		MusicManager._instance = self
		self.device = aud.Device()

		self.base_volume = args.get("Music Volume", 0.8)
		self.sfx_volume = args.get("SFX Volume", 1.0)
		self.default_fade = args.get("Fade Time", 2.0)
		
		# Setup da UI
		self.ui_scene_name = args.get("UI Scene", "0_SCN_Systen")
		self.ui_spawner = args.get("UI Spawner", "msg_status")
		self.music_popup = args.get("Music Popup", "Msg_Music")
		self.popup_lifetime = args.get("Popup Lifetime", 200)

		# Playlists (Apelidos organizados)
		self.music_playlist = {
			"MENU": "musica_menu.ogg",
			"music_1": "We Ride - Reed Mathis.ogg",
			"VICTORY": "win_song.wav",
		}
		
		self.sfx_playlist = {
			"Sweep10": "Shot_Short_Sweep10.ogg",
			"Sweep17": "Shot_Short_Sweep17.ogg",
		}

		# Estado
		self.handle = None
		self.fade_mode = None  # "in", "out"
		self.fade_timer = 0.0
		self.fade_dur = 0.0

		# Fila para troca
		self.next_factory = None

		# Cache de caminhos para evitar acessar o disco repetidamente
		self.path_cache = {}

	def start(self, args):
		pass

	def _get_vol(self):
		master = logic.globalDict.get("Config", {}).get("MasterVolume", 1.0)
		return self.base_volume * master

	def _resolve(self, name):
		# 0. Se já procuramos esse arquivo antes, retorna da memória! (Custo zero)
		if name in self.path_cache:
			return self.path_cache[name]

		# Verifica se é apelido na playlist de musicas ou de SFX
		filename = self.music_playlist.get(name, self.sfx_playlist.get(name, name))

		# Lista de locais para procurar (Ordem de prioridade)
		search_paths = [
			"//sounds/music/",  # Prioridade 1: Musicas
			"//sounds/sfx/",    # Prioridade 2: Efeitos sonoros
			"//sounds/",        # Prioridade 3: Pasta geral
			"//"                # Prioridade 4: Raiz
		]

		for folder in search_paths:
			base_path = logic.expandPath(folder + filename)

			# 1. Tenta o arquivo exato
			if os.path.exists(base_path):
				self.path_cache[name] = base_path
				return base_path

			# 2. Tenta com extensões comuns (caso você tenha esquecido)
			if "." not in filename:
				for ext in [".ogg", ".mp3", ".wav"]:
					if os.path.exists(base_path + ext):
						found_path = base_path + ext
						self.path_cache[name] = found_path
						return found_path

		return None

	def play(self, name, loop=-1, fade_time=None):
		path = self._resolve(name)
		if not path:
			print(f"[Music] Erro: {name} nao encontrado.")
			return

		try:
			# Carrega SEM cache (Stream do disco)
			factory = aud.Sound(path)
		except Exception as e:
			print(f"[MusicManager] Erro ao carregar/decodificar musica '{path}': {e}")
			return

		time = fade_time if fade_time is not None else self.default_fade

		# Se já tem musica tocando, faz fade out antes
		if self.handle and self.handle.status == aud.STATUS_PLAYING:
			self.next_factory = (factory, loop, time)
			self._start_fade("out", time)
		else:
			self._start_immediate(factory, loop, time)

		# Dispara o Popup indicando qual música começou a tocar
		self._spawn_popup(name)

	def play_sfx(self, name, vol=None, pitch=1.0):
		"""Toca um efeito sonoro instantaneamente, sem loop e sem interromper a musica atual."""
		path = self._resolve(name)
		if not path:
			print(f"[MusicManager] SFX AVISO: Efeito '{name}' nao encontrado.")
			return None

		try:
			factory = aud.Sound(path)
			sfx_handle = self.device.play(factory)
			
			if sfx_handle:
				sfx_handle.loop_count = 0
				master = logic.globalDict.get("Config", {}).get("MasterVolume", 1.0)
				final_vol = vol if vol is not None else self.sfx_volume
				sfx_handle.volume = final_vol * master
				sfx_handle.pitch = pitch
				
			return sfx_handle
		except Exception as e:
			print(f"[MusicManager] Erro ao carregar/tocar SFX '{path}': {e}")
			return None

	def _spawn_popup(self, track_name):
		"""Instancia o objeto de UI na cena Mestra e atualiza seu texto"""
		spawner = None
		spawner_scene = None
		
		# 1. Encontra a Cena de UI e o Spawner
		for scene in Range.logic.getSceneList():
			if scene.name == self.ui_scene_name:
				spawner = scene.objects.get(self.ui_spawner)
				spawner_scene = scene
				break

		# 2. Procura o objeto original (matriz) nas layers inativas de TODAS as cenas carregadas
		obj_matrix = None
		for scene in Range.logic.getSceneList():
			obj_matrix = scene.objectsInactive.get(self.music_popup)
			if obj_matrix:
				break

		# 3. Faz o Spawn na cena correta
		if spawner_scene and spawner and obj_matrix:
			obj = spawner_scene.addObject(obj_matrix, spawner, self.popup_lifetime)
			if "Text" in obj:
				obj["Text"] = f"Musica - {track_name}"
		else:
			print(f"[MusicManager] AVISO: Popup nao instanciado. Spawner '{self.ui_spawner}' encontrado? {bool(spawner)}. Objeto '{self.music_popup}' encontrado? {bool(obj_matrix)}.")

	def stop(self, fade_time=None):
		"""Realiza um Fade Out suave e para a musica completamente."""
		time = fade_time if fade_time is not None else self.default_fade
		if self.handle and self.handle.status == aud.STATUS_PLAYING:
			self.next_factory = None  # Cancela qualquer musica agendada
			self._start_fade("out", time)
		elif self.handle:
			self.handle.stop()

	def _start_immediate(self, factory, loop, time):
		self.handle = self.device.play(factory)
		self.handle.loop_count = loop
		self.handle.volume = 0.0
		self._start_fade("in", time)

	def _start_fade(self, mode, duration):
		self.fade_mode = mode
		self.fade_dur = max(0.01, duration)
		self.fade_timer = 0.0

		if self.handle:
			self.fade_start = self.handle.volume if mode == "out" else 0.0
			self.fade_target = 0.0 if mode == "out" else self._get_vol()

	def volume_update(self):
		"""Monitora mudanças de volume em tempo real (Menu de Opções)"""
		# Só atualiza se NÃO estiver fazendo fade (transição)
		if self.handle and not self.fade_mode:
			target = self._get_vol()
			# Pequena otimização: só muda se a diferença for maior que 1%
			if abs(self.handle.volume - target) > 0.01:
				self.handle.volume = target

	def update(self):
		# --- CAIXA DE CORREIO (Ouvinte Global) ---
		# Verifica se alguém mandou um comando para trocar de música
		command = logic.globalDict.get("Music")
		if command:
			if command == "STOP":
				self.stop()
			else:
				self.play(command)
			del logic.globalDict["Music"]  # Destrói a mensagem após executá-la

		# Verifica se alguém mandou um comando de Efeito Sonoro (SFX)
		sfx_command = logic.globalDict.get("SFX")
		if sfx_command:
			self.play_sfx(sfx_command)
			del logic.globalDict["SFX"]

		# --- CAIXA DE CORREIO (Ouvinte via Logic Bricks - Message Sensor) ---
		# Permite receber comandos via Atuador de Mensagem
		for sensor in self.object.sensors:
			if hasattr(sensor, "subjects") and sensor.positive:
				for subject, body in zip(sensor.subjects, sensor.bodies):
					if subject == "Music":
						if body == "STOP":
							self.stop()
						elif body:
							self.play(body)
					elif subject == "SFX":
						if body:
							self.play_sfx(body)

		self.volume_update()
		# Lógica de Fade
		if self.fade_mode and self.handle:
			dt = logic.deltaTime()
			self.fade_timer += dt
			t = min(self.fade_timer / self.fade_dur, 1.0)

			vol = self.fade_start + (self.fade_target - self.fade_start) * t
			self.handle.volume = vol

			if t >= 1.0:
				if self.fade_mode == "out":
					self.handle.stop()
					self.fade_mode = None
					# Toca a próxima
					if self.next_factory:
						fac, loop, time = self.next_factory
						self._start_immediate(fac, loop, time)
						self.next_factory = None
				else:
					self.fade_mode = None
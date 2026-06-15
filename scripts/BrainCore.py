import Range
from collections import OrderedDict

# --- TRATAMENTO PARA A INTERFACE DO BLENDER ---
# Impede crashes quando a interface lê as teclas
try:
    from Range import events
except:
    class FakeEvents:
        def __getattr__(self, name): return 0
    events = FakeEvents()

class BrainCore(Range.types.KX_PythonComponent):
    # Configuração da Interface na Range Engine
    args = OrderedDict([
        ("C_Icons", "SEQUENCE"),  # Ícone sugerido para o Core

        ("C_Header /Geral/SETTINGS", True),
        ("Start Scene", "SCN_Main_Menu"),  # Qual cena carregar ao abrir o jogo?
        ("Menu Scenes", "SCN_Main_Menu"),  # Cenas de Menu (separadas por vírgula)
        ("Debug Mode", True),  # Mostrar prints no console?
        ("Show Mouse (Game)", False), # O mouse fica visível durante o jogo?

        ("C_Header /Loading/TIME", True),
        ("Loading Scene", "SCN_Load"), # Nome da cena de Loading
        ("Loading Time", 1.1), # Tempo mínimo de tela de loading (segundos)
        
        ("C_Header /Pause/PAUSE", True),
        ("Allow Pause", True), # Permite pausar o jogo?
        ("Pause Scene", "SCN_Pause"), # Nome da cena de Pause
        ("Pause Key", "ESCKEY"), # Tecla para pausar o jogo
    ])

    def awake(self, args):
        # --- Proteção Singleton (Inspirado no RolimaRacer) ---
        # Impede que cópias fantasmas do BrainCore existam e causem bugs
        existente = Range.logic.globalDict.get("BrainCore_Obj")
        if existente and not existente.invalid and existente != self.object:
            print(f"[BrainCore] Copia intrusa detectada na cena '{self.object.scene.name}'. Auto-destruindo.")
            self.object.endObject()
            return

        # Garante que o BrainCore seja único e acessível
        # Cria uma referência global para ele mesmo no objeto
        self.object["core_instance"] = self
        # Registra o Objeto BrainCore globalmente para outros scripts (ex: Botões) acharem
        Range.logic.globalDict["BrainCore_Obj"] = self.object

        # Inicializa variáveis internas
        self.active_scene_name = None
        
        self.loading_scene_name = args.get("Loading Scene", "SCN_Load")
        self.allow_pause = args.get("Allow Pause", True)
        self.pause_scene_name = args.get("Pause Scene", "SCN_Pause")
        self.is_paused = False
        self.loading_time = args.get("Loading Time", 0.5)
        self.is_loading = False
        self._load_state = 0
        self._target_scene = ""
        self._load_timer = 0.0
        self._load_frames = 0
        
        # Status Global do Jogo (MENU, PLAYING, PAUSED, LOADING)
        Range.logic.globalDict["PAUSED"] = False
        Range.logic.globalDict["GAME_STATE"] = "LOADING"
        
    def start(self, args):
        # --- PROTEÇÃO DA ARQUITETURA (BASE SCENE) ---
        # Na Range/UPBGE, se a cena Base for fechada, TODAS as outras morrem junto!
        base_scene = Range.logic.getSceneList()[0]
        if base_scene.name != self.object.scene.name:
            print("\n" + "="*65)
            print(f"[ERRO FATAL DA ARQUITETURA] A '{self.object.scene.name}' NAO e a Cena Base!")
            print(f"O jogo foi iniciado a partir da cena: '{base_scene.name}'")
            print(f"Se a '{base_scene.name}' for recarregada, o BrainCore morrera junto.")
            print("REGRA: Voce DEVE dar o Play inicial SEMPRE estando na cena do Sistema!")
            print("="*65 + "\n")
            
        # --- Captura Argumentos ---
        self.start_scene_name = args["Start Scene"]
        self.menu_scenes = [s.strip() for s in args.get("Menu Scenes", "SCN_Main_Menu").split(",")]
        self.debug = args["Debug Mode"]
        self.default_mouse = args.get("Show Mouse (Game)", False)
        
        # Aplica a visibilidade inicial do mouse
        Range.render.showMouse(self.default_mouse)
        
        # --- Controles ---
        self.pause_key = getattr(events, args.get("Pause Key", "ESCKEY"), events.ESCKEY)
        self.keyboard = Range.logic.keyboard

        # --- EXEMPLO DE COMO PUXAR OS SUB-SISTEMAS COM SEGURANÇA ---
        try:
            from scripts.SaveManager import SaveManager
            # self.save = SaveManager.get()
        except ImportError:
            pass

        # --- Carrega a Primeira Cena (Menu) ---
        # Adiciona diretamente a cena inicial para não exibir a tela de Loading na abertura
        self.safe_add_scene(self.start_scene_name, is_overlay=False)
        self.active_scene_name = self.start_scene_name
        
        # Atualiza o Estado Global baseado no tipo de cena
        if self.active_scene_name in self.menu_scenes:
            Range.logic.globalDict["GAME_STATE"] = "MENU"
            Range.render.showMouse(True)
        else:
            Range.logic.globalDict["GAME_STATE"] = "PLAYING"
            Range.render.showMouse(self.default_mouse)

    def update(self):
        # --- CAIXA DE CORREIO (Interface e Botoes) ---
        # Permite comandos diretos via globalDict
        cmd_load = Range.logic.globalDict.get("LoadScene")
        if cmd_load:
            self.load_level(cmd_load)
            del Range.logic.globalDict["LoadScene"]

        cmd_load_direct = Range.logic.globalDict.get("LoadSceneDirect")
        if cmd_load_direct:
            self.load_level(cmd_load_direct, show_loading=False)
            del Range.logic.globalDict["LoadSceneDirect"]

        # Permite comandos via Logic Bricks (Message Actuator)
        for sensor in self.object.sensors:
            if hasattr(sensor, "subjects") and sensor.positive:
                for subject, body in zip(sensor.subjects, sensor.bodies):
                    if subject == "LoadScene" and body:
                        self.load_level(body)
                    elif subject == "LoadSceneDirect" and body:
                        self.load_level(body, show_loading=False)
                    elif subject == "TogglePause":
                        if not self.is_loading and self.active_scene_name and self.allow_pause and Range.logic.globalDict.get("GAME_STATE") in ["PLAYING", "PAUSED"]:
                            self.toggle_pause()
                    elif subject == "QuitGame":
                        Range.logic.endGame()

        # Máquina de Estados para Transição de Cenas com Tela de Loading
        if self.is_loading:
            if self._load_state == 1:
                # 1. Adiciona a tela de load (Regra: Overlay para cobrir tudo durante a transição)
                self.safe_add_scene(self.loading_scene_name, is_overlay=True)
                self._load_state = 2
                self._load_timer = 0.0
                self._load_frames = 0
                
            elif self._load_state == 2:
                # O Segredo do SceneLoader.py do RolimaRacer!
                # Espera 5 frames para a engine desenhar a tela de load ANTES de travar a thread.
                self._load_frames += 1
                if self._load_frames > 5:
                    self._nuke_old_scenes()
                    self._load_state = 3
                
            elif self._load_state == 3:
                # 3. Adiciona a nova fase usando a regra de hierarquia
                self.safe_add_scene(self._target_scene, is_overlay=False)
                self._load_state = 4
                
            elif self._load_state == 4:
                # 4. Aguarda o tempo mínimo e garante que a engine carregou a cena
                self._load_timer += Range.logic.deltaTime()
                if self._load_timer >= self.loading_time:
                    # Remove a tela de load aplicando regras
                    self.safe_end_scene(self.loading_scene_name)
                            
                    self.active_scene_name = self._target_scene
                    self.is_loading = False
                    self._load_state = 0
                    
                    # Atualiza o Estado Global baseado no tipo de cena
                    if self.active_scene_name in self.menu_scenes:
                        Range.logic.globalDict["GAME_STATE"] = "MENU"
                        Range.render.showMouse(True)
                    else:
                        Range.logic.globalDict["GAME_STATE"] = "PLAYING"
                        Range.render.showMouse(self.default_mouse)

        # Lógica de Pause (só funciona se não estiver no meio de um Loading)
        elif not self.is_loading and self.active_scene_name and self.allow_pause and Range.logic.globalDict.get("GAME_STATE") in ["PLAYING", "PAUSED"]:
            pause_input = self.keyboard.inputs[self.pause_key]
            if getattr(pause_input, "activated", False):
                self.toggle_pause()

    # --- FUNÇÕES PERSONALIZADAS DO SISTEMA ---

    def _nuke_old_scenes(self):
        """         
        Fecha todas as cenas filhas, deixando apenas o Sistema e a Tela de Loading.
        """
        system_name = self.object.scene.name
        for scn in Range.logic.getSceneList():
            if scn.name not in [system_name, self.loading_scene_name]:
                scn.end()

    def safe_add_scene(self, scene_name, is_overlay=False):
        """
        Regra 1: Toda cena criada passa por aqui.
        Ao adicionar como is_overlay=False (Background/0), garantimos que
        a cena Mestra (0_SCN_Systen) fique sempre na frente.
        """
        if not scene_name: return
        mode = 1 if is_overlay else 0
        Range.logic.addScene(scene_name, mode)

    def safe_end_scene(self, scene_name):
        """
        Regra 2: Bloqueio contra suicídio do sistema. 
        Proíbe terminantemente o fechamento da Cena Mestra.
        """
        if not scene_name: return
        system_scene_name = self.object.scene.name
        if scene_name == system_scene_name:
            print(f"[BrainCore] ⚠ BLOQUEADO: Tentativa de fechar a cena Mestra '{scene_name}' impedida!")
            return
            
        for scn in Range.logic.getSceneList():
            if scn.name == scene_name:
                scn.end()
                break

    def load_level(self, scene_name, show_loading=True):
        """Inicia a transição segura de cenas"""
        if self.is_loading: return
        
        # Proteção extra: O BrainCore nunca deve tentar carregar a si mesmo como Fase
        if scene_name == self.object.scene.name:
            print(f"[BrainCore] ERRO: Nao se pode carregar a Cena Mestra como fase ({scene_name})!")
            return
        
        # Se estiver pausado, remove o pause para a transição (loading) ser limpa
        if self.is_paused:
            self.toggle_pause()

        self._target_scene = scene_name
        
        if show_loading:
            self.is_loading = True
            self._load_state = 1
            Range.logic.globalDict["GAME_STATE"] = "LOADING"
        else:
            # Carregamento Direto (Ideal para menus rápidos)
            self._nuke_old_scenes()
            self.safe_add_scene(self._target_scene, is_overlay=False)
            self.active_scene_name = self._target_scene
            
            if self.active_scene_name in self.menu_scenes:
                Range.logic.globalDict["GAME_STATE"] = "MENU"
                Range.render.showMouse(True)
            else:
                Range.logic.globalDict["GAME_STATE"] = "PLAYING"
                Range.render.showMouse(self.default_mouse)

    def toggle_pause(self):
        """Pausa ou despausa o jogo, gerenciando a cena de pause"""
        self.is_paused = not self.is_paused
        
        system_scene_name = self.object.scene.name
        
        if self.is_paused:
            # Suspende TODAS as cenas ativas (incluindo possíveis HUDs extras), exceto a do Sistema
            for scn in Range.logic.getSceneList():
                if scn.name not in [system_scene_name, self.loading_scene_name, self.pause_scene_name]:
                    scn.suspend()
            
            # Adiciona a cena de Pause como Overlay (Cobre o jogo e a UI do Sistema)
            self.safe_add_scene(self.pause_scene_name, is_overlay=True)
            
            Range.logic.globalDict["PAUSED"] = True
            Range.logic.globalDict["GAME_STATE"] = "PAUSED"
            Range.render.showMouse(True)
        else:
            # Retoma TODAS as cenas que foram suspensas
            for scn in Range.logic.getSceneList():
                if scn.name not in [system_scene_name, self.loading_scene_name, self.pause_scene_name]:
                    scn.resume()
                    
            # Garante que a velocidade do jogo seja normalizada
            Range.logic.setTimeScale(1.0)
            
            # Remove a cena de Pause seguindo as regras
            self.safe_end_scene(self.pause_scene_name)
            
            Range.logic.globalDict["PAUSED"] = False
            Range.logic.globalDict["GAME_STATE"] = "PLAYING"
            Range.render.showMouse(self.default_mouse)

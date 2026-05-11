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
		("Music Volume", 0.8),
		("Fade Time", 2.0)
	])

	@staticmethod
	def get():
		return MusicManager._instance

	def awake(self, args):
		MusicManager._instance = self
		self.device = aud.Device()

		self.base_volume = args["Music Volume"]
		self.default_fade = args["Fade Time"]

		# Playlist (Apelidos)
		self.playlist = {
			"MENU": "musica_menu.ogg",
			"RACE_1": "track_forest.mp3",
			"VICTORY": "win_song.wav"
		}

		# Estado
		self.handle = None
		self.fade_mode = None  # "in", "out"
		self.fade_timer = 0.0
		self.fade_dur = 0.0

		# Fila para troca
		self.next_factory = None

	def _get_vol(self):
		master = logic.globalDict.get("Config", {}).get("MasterVolume", 1.0)
		return self.base_volume * master

	def _resolve(self, name):
		# Verifica se é apelido da playlist
		filename = self.playlist.get(name, name)

		# Lista de locais para procurar (Ordem de prioridade)
		search_paths = [
			"//sounds/music/",  # Prioridade 1: Pasta organizada
			"//sounds/",  # Prioridade 2: Pasta geral
			"//"  # Prioridade 3: Raiz
		]

		for folder in search_paths:
			base_path = logic.expandPath(folder + filename)

			# 1. Tenta o arquivo exato
			if os.path.exists(base_path):
				return base_path

			# 2. Tenta com extensões comuns (caso você tenha esquecido)
			if "." not in filename:
				for ext in [".ogg", ".mp3", ".wav"]:
					if os.path.exists(base_path + ext):
						return base_path + ext

		return None

	def play(self, name, loop=-1, fade_time=None):
		path = self._resolve(name)
		if not path:
			print(f"[Music] Erro: {name} nao encontrado.")
			return

		# Carrega SEM cache (Stream do disco)
		factory = aud.Sound(path)

		time = fade_time if fade_time is not None else self.default_fade

		# Se já tem musica tocando, faz fade out antes
		if self.handle and self.handle.status == aud.STATUS_PLAYING:
			self.next_factory = (factory, loop, time)
			self._start_fade("out", time)
		else:
			self._start_immediate(factory, loop, time)

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
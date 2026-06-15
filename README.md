# 🚀 Start Setup - Range Engine

Um template base robusto para acelerar o desenvolvimento de jogos utilizando a **Range Engine**. Este projeto fornece uma arquitetura segura e sistemas essenciais pré-configurados para que você possa focar direto na criação do seu jogo, sem precisar reinventar a roda.

## ✨ Recursos Inclusos

* 🧠 **BrainCore (Scene Manager):** Sistema central de gerenciamento de fluxo do jogo. Protege a arquitetura da cena base (System) e gerencia transições seguras de fases com **telas de loading** (ou carregamento direto) e um **sistema de pause global inteligente**.
* 💾 **Save Manager:** Sistema completo de Save/Load em `JSON`. Ele escaneia as fases, salva a posição, rotação e propriedades (props) dos objetos na memória. Também é capaz de re-spawnar instâncias dinâmicas e limpar objetos destruídos de forma inteligente.
* 🎵 **Music Manager:** Gerenciador de trilhas sonoras focado em polimento. Controla automaticamente transições suaves de volume (*Fade In/Fade Out*) e gerencia sua playlist através de apelidos (aliases), integrando-se facilmente com o sistema de volume global do jogo.

## 📜 Regras de Funcionamento (Como Usar)

**🧠 1. Regras do BrainCore (Gerenciamento de Cenas)**
* **A Regra de Ouro:** O jogo DEVE ser iniciado (Play) sempre a partir da cena Mestra (`0_SCN_Systen`). Se ela for fechada ou não for a primeira, a arquitetura do jogo quebra.
* **Troca de Fases:** Não utilize os atuadores padrão da engine para trocar de cena.
  * **Com Loading:** Envie uma Mensagem (`Message Actuator`) com o Assunto (Subject) `"LoadScene"` e o nome da fase no Corpo (Body). Ou use via Python: `Range.logic.globalDict["LoadScene"] = "nome_da_fase"`.
  * **Sem Loading (Direto):** Envie `"LoadSceneDirect"` para trocas instantâneas (ideal para transição rápida entre menus).
* **Pausa Global Inteligente:** Ao enviar a mensagem `"TogglePause"`, o BrainCore rastreia e congela **todas** as cenas ativas do jogo (fases, minimapas, HUDs extras), garantindo que nada rode no fundo. Ao despausar, a velocidade (`TimeScale`) é normalizada.
* **Ordem de Renderização (O "Sanduíche" de Cenas):** A engine desenha as telas em 3 camadas de profundidade (de trás para frente):
  1. **Lá no Fundo (Background):** A fase do jogo (ex: `Fase_1`).
  2. **No Meio (Base):** A cena Mestra (`0_SCN_Systen`). Fica na frente da fase, permitindo que HUDs e notificações globais apareçam sobre o jogo.
  3. **Na Frente de Tudo (Overlay):** Telas de Pause e Loading. Cobrem absolutamente tudo, escondendo a fase e a interface da cena Mestra.

**💾 2. Regras do Save Manager (Persistência)**
* **O que é salvo:** O sistema rastreia e salva automaticamente a Posição, Rotação e Propriedades de objetos Físicos (Dinâmicos/Character), *Empties* e *Group Instances*.
* **O que é ignorado:** Propriedades de uso exclusivo da interface da Range Engine (que começam com `C_`) são ignoradas para economizar espaço no JSON.
* **Restauração Dinâmica:** Ao dar Load, se houverem objetos extras na cena atual (que não existiam no save), eles são deletados. Se faltarem objetos, o sistema busca o original na layer inativa (oculta) e o spawna novamente na posição correta.

**🎵 3. Regras do Music Manager (Áudio)**
* **Uso de Apelidos (Aliases):** O sistema usa um dicionário interno (Playlist). Em vez de chamar `"track_forest.mp3"`, você dá o play chamando um apelido como `"RACE_1"`.
* **Busca Inteligente:** Você não precisa passar o caminho completo. O sistema busca automaticamente o áudio nas pastas `//sounds/music/` ou `//sounds/`, testando extensões comuns (`.ogg`, `.mp3`, `.wav`) caso você tenha esquecido de informar.
* **Fades Automáticos:** Nunca zere o volume bruscamente. Ao mandar tocar uma nova música, se já houver uma tocando, o gerenciador fará o *Fade Out* (redução suave) da atual e o *Fade In* da nova sozinho.
* 
<img width="1024" height="1536" alt="image" src="https://github.com/user-attachments/assets/36ab866d-5ade-4d8b-aa53-02fd5dd670bc" />

---

### 🛠️ Configuração e Instalação
1. Clone o repositório ou baixe o arquivo ZIP.
2. Abra o projeto através da **Range Engine**.
3. Para testar o sistema, abra a cena `0_SCN_Systen` e inicie o jogo (P). O `BrainCore` fará a transição e a carga dos menus/fases automaticamente.

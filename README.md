# SuperTuxKart — Face Tracking Controller (Solo & Collaborative)

Contrôleur de jeu interactif pour **SuperTuxKart** basé sur la vision par ordinateur (**MediaPipe Face Tracking**), la détection d'objets colorés et des capteurs physiques embarqués (**Arduino**).

Le système permet de piloter un kart en **Solo** (un seul joueur gère tout avec le visage) ou en **Duo Collaboratif** (deux joueurs se partagent le contrôle : l'un tourne, l'autre accélère/freine).

---

## 🎮 Résumé des Contrôles

| Action dans STK | Touche Clavier | Source de Contrôle |
| :--- | :--- | :--- |
| **Direction Gauche / Droite** | <kbd>←</kbd> / <kbd>→</kbd> | **Caméra (Visage P1 / Solo)** : Inclinaison de la tête (`--steering face`) ou Position horizontale (`--steering position`) |
| **Accélération** | <kbd>↑</kbd> | **Caméra (Profondeur $Z$ P2 / Solo)** : Se rapprocher de la webcam |
| **Frein / Marche Arrière** | <kbd>↓</kbd> | **Caméra (Profondeur $Z$ P2 / Solo)** : S'éloigner / reculer de la webcam |
| **Tir d'Objet (`FIRE`)** | <kbd>Espace</kbd> | **Caméra (Objet coloré)** : Présenter une carte/objet vert(e) ou rouge devant la caméra |
| **Dérapage (`Drift`)** | <kbd>V</kbd> | **Capteur Musculaire EMG (Arduino A0)** : Contraction musculaire (toggle ON/OFF) |
| **Nitro** | <kbd>N</kbd> | **Capteur de Vibration (Arduino Pin 2)** : Coup / secousse sur le capteur |
| **Sauvetage (`Rescue`)** | <kbd>Retour arrière</kbd> | **Gyroscope / Accéléromètre** : Secousse physique rapide de la carte |

---

## 🚀 Démarrage Rapide

### Prérequis
Assurez-vous que l'environnement virtuel Python est prêt et activé :
```bash
source .venv/bin/activate
```

---

### Méthode 1 : Lancement Tout-en-Un (Recommandé)

1. **Terminal 1 — Lancer le jeu et le serveur d'entrées :**
   ```bash
   ./launch_game.sh
   ```
   *(Entrez votre mot de passe `sudo` si demandé, nécessaire pour l'injection des touches sous Linux).*

2. **Terminal 2 — Lancer le contrôleur de visage :**

   - **Mode Duo Collaboratif (2 Joueurs) :**
     ```bash
     .venv/bin/python SetUp_Collab/STK_collab_input.py --mode duo --steering position --color green
     ```

   - **Mode Solo (1 Joueur) :**
     ```bash
     .venv/bin/python SetUp_Collab/STK_collab_input.py --mode solo --steering position --color green
     ```

---

### Méthode 2 : Lancement Manuel Composant par Composant

Si vous préférez lancer chaque élément séparément :

```bash
# Terminal 1 : Serveur de frappe de touches (UDP 6006)
sudo .venv/bin/python SetUp_Collab/STK_input_server.py

# Terminal 2 : SuperTuxKart
/home/paulo/SIIA/MCSI/SuperTuxKart-1.2-linux/run_game.sh

# Terminal 3 : Contrôleur de tracking collaboratif
.venv/bin/python SetUp_Collab/STK_collab_input.py --mode duo --steering position --color green
```

---

## 👥 Modes de Jeu

### 1. Mode Duo Collaboratif (`--mode duo`)
Deux joueurs se tiennent côte à côte devant la webcam :
- **Joueur 1 (Visage à Gauche sur l'écran miroir)** : Contrôle la **Direction**.
- **Joueur 2 (Visage à Droite sur l'écran miroir)** : Contrôle la **Vitesse** (Accélération / Freinage).
- **Les deux joueurs** peuvent présenter une carte colorée pour tirer des objets.

### 2. Mode Solo (`--mode solo`)
Un seul joueur contrôle la totalité du kart :
- Direction avec la tête.
- Accélération / freinage en s'approchant ou s'éloignant de la webcam.
- Tir d'objets avec la carte colorée.

### 3. Mode Automatique (`--mode auto`, défaut)
Bascule automatiquement en **Duo** lorsque 2 visages sont détectés, et repasse en **Solo** si une seule personne est présente.

---

## 🎯 Options de Direction (`--steering`)

Le script supporte deux modes de direction selon vos préférences :

1. **Mode Position Horizontale (`--steering position`) :**
   - Décalez la tête latéralement à gauche ou à droite au-delà des repères visuels affichés à l'écran.
   - Les repères changent dynamiquement de couleur (cyan au repos, vert vif en braquage).
   - Plus vous dépassez la ligne, plus le braquage est intense (modulation PWM).

2. **Mode Inclinaison de la Tête (`--steering face`, défaut) :**
   - Penchez la tête vers la droite ou la gauche.
   - L'angle est mesuré entre les deux yeux.
   - Calibrage automatique de la position neutre pendant les 2 premières secondes.

---

## 🎨 Détection d'Objets Colorés (`--color`)

Pour tirer des objets en jeu sans appuyer sur le clavier, présentez un objet ou un carton de couleur devant la webcam :

- **Couleurs prédéfinies :** `--color green` (défaut), `--color red`, `--color blue`, `--color yellow`, `--color orange`.
- **Désactiver :** `--color off`.
- **Calibrage instantané en direct (<kbd>C</kbd>) :**
  Dans la fenêtre webcam, placez votre objet dans le rectangle central et appuyez sur la touche <kbd>C</kbd>. L'algorithme échantillonne automatiquement la couleur et ajuste les seuils HSV à l'éclairage de votre pièce !

Pour le guide complet des réglages de détection de couleur, consultez :
[`SetUp_Collab/color_detection_guide.md`](SetUp_Collab/color_detection_guide.md).

---

## 🧪 Tester Uniquement la Caméra (Sans le Jeu)

Pour vérifier votre cadrage, le flux miroir, la détection des visages et calibrer votre carte de couleur sans lancer SuperTuxKart :

```bash
.venv/bin/python SetUp_Collab/face_tracking.py --steering position --color green
```
- <kbd>C</kbd> : Échantillonner la couleur au centre de l'écran.
- <kbd>ESC</kbd> ou <kbd>Q</kbd> : Quitter.

---

## 📁 Structure du Projet

```text
├── launch_game.sh                # Script de lancement tout-en-un (Serveur + STK)
├── README.md                     # Documentation du projet
├── SetUp_Collab/                 # Module de contrôle collaboratif actif
│   ├── STK_collab_input.py       # Récepteur OSC, logique de jeu et Arduino
│   ├── STK_input_server.py       # Serveur UDP récepteur injectant les touches
│   ├── face_tracking.py          # Vision MediaPipe BlazeFace, HUD et OSC
│   ├── STK_Sender.py             # Client d'envoi UDP vers le serveur
│   ├── color_detection_guide.md  # Guide de calibration des couleurs
│   ├── blaze_face_short_range.tflite # Modèle MediaPipe Face
│   ├── classes/
│   │   ├── config.py             # Constantes, seuils, dimensions et OSC
│   │   ├── colorDetector.py      # Détecteur robuste de cartes colorées
│   │   ├── actionDetector.py     # Détection des secousses et gestes
│   │   ├── KartState.py          # État du kart et commandes
│   │   └── sensorStates.py       # Structures d'état et écouteurs OSC
│   └── main/                     # Code Arduino capteurs physiques
│       ├── main.ino              # Firmware Arduino (muscle + vibration)
│       └── Sensors/              # Classes C++ des capteurs
└── SetUp_Performance/            # Versions de référence antérieures
```
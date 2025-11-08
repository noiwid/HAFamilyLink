# 📱 Google Family Link pour Home Assistant

Salut la commu ! 👋

Je partage avec vous mon intégration **Google Family Link pour Home Assistant**. Ça fait un moment que je voulais pouvoir gérer les appareils de mes enfants directement depuis HA, et voilà le résultat !

## 🙏 Remerciements

Avant tout, je tiens à remercier :
- **[@tducret](https://github.com/tducret/familylink)** pour son package Python original qui a documenté les premiers endpoints de l'API Google Family Link
- **[@Vortitron](https://github.com/Vortitron/HAFamilyLink)** pour son travail initial sur HAFamilyLink qui a servi de base à ce projet
- **La communauté Home Assistant** pour l'inspiration et les nombreux exemples d'intégrations
- **L'équipe Playwright** pour leur excellent framework d'automation de navigateur
- **Claude (Anthropic)** qui m'a accompagné dans le développement et la résolution de nombreux défis techniques
- **Tous ceux qui ont partagé leurs connaissances** sur le reverse engineering d'APIs Google

Sans ces briques, ce projet n'aurait jamais vu le jour !

---

## 🎯 C'est quoi ?

En gros, ça vous permet de **piloter et surveiller les appareils Family Link** directement depuis Home Assistant. Temps d'écran, verrouillage/déverrouillage à distance, stats d'utilisation des apps... tout est récupérable et automatisable !

## ✨ Ce que ça fait

### 🔐 Contrôle des appareils
- **Verrouiller/déverrouiller à distance** via des switches
- **Synchro dans les 2 sens** : si vous changez quelque chose dans l'app Family Link, HA le voit aussi
- **Multi-appareils** : gérez tous les téléphones/tablettes de vos enfants

### 📊 Suivi du temps d'écran
- **Temps d'écran du jour** en temps réel
- **Top 10 des apps** les plus utilisées avec les stats
- **Détail par app** (heures, minutes, secondes)
- **Rafraîchissement auto** toutes les 5 minutes (modifiable)

### 📲 Gestion des apps
- **Nombre d'apps installées**
- **Apps bloquées** avec la liste
- **Apps avec limites de temps**
- **Détails** : noms, limites, etc.

### 👶 Infos sur l'enfant
- **Profil** : nom, email, date de naissance, âge
- **Infos appareil** : modèle, nom, dernière activité
- **Membres de la famille** avec leurs rôles

## 🏗️ Comment ça marche ?

Le projet a **2 parties** qui bossent ensemble :

### 1. **L'Add-on** (obligatoire)
C'est lui qui gère la connexion à Google :
- Lance un navigateur Chromium avec Playwright
- **Serveur VNC intégré** (port 5900) pour que vous puissiez vous connecter à Google
- Gère la 2FA (SMS, appli authenticator, notifs push)
- Stocke les cookies de façon chiffrée
- Rafraîchit l'auth automatiquement

### 2. **L'intégration HA**
C'est elle qui récupère les données et contrôle les appareils :
- Config flow pour installer facilement
- Communique avec l'API Google Family Link
- Gère les mises à jour des données
- Crée les capteurs et switches dans HA

**Pourquoi 2 parties ?** Parce que Docker de HA n'aime pas trop les navigateurs. Du coup l'add-on tourne à part avec Chromium, et l'intégration s'occupe du reste.

## 🔐 Comment se connecter

Vous allez avoir besoin d'un **client VNC** (TightVNC, RealVNC, ou VNC Viewer) :

1. **Lancez l'add-on** Family Link Auth
2. **Ouvrez l'interface web** (http://[IP_HA]:8099)
3. **Cliquez sur** "Démarrer l'authentification"
4. **Connectez-vous en VNC** :
   - **Adresse** : `[IP_HA]:5900`
   - **Mot de passe** : `familylink`
5. **Une fenêtre Chromium s'ouvre** dans VNC
6. **Loguez-vous à Google** :
   - Email
   - Mot de passe
   - Code 2FA si vous en avez un
7. **C'est bon !** Les cookies sont sauvegardés automatiquement ✅

**Pourquoi VNC ?** Parce que le navigateur tourne dans le conteneur Docker, et VNC c'est le seul moyen de "voir" la fenêtre pour se connecter.

**Clients VNC dispo :**
- **Windows/Mac/Linux** : [TightVNC](https://www.tightvnc.com/) ou [RealVNC](https://www.realvnc.com/)
- **iOS** : VNC Viewer (App Store)
- **Android** : VNC Viewer (Google Play)

## 💡 Exemples d'automatisations

### Verrouillage au coucher
```yaml
automation:
  - alias: "Verrouiller le téléphone à l'heure du coucher"
    trigger:
      - platform: time
        at: "21:00:00"
    condition:
      - condition: time
        weekday: [mon, tue, wed, thu, fri]
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.telephone_enfant
```

### Alerte temps d'écran excessif
```yaml
automation:
  - alias: "Alerte si temps d'écran excessif"
    trigger:
      - platform: numeric_state
        entity_id: sensor.family_link_daily_screen_time
        above: 180  # 3 heures en minutes
    action:
      - service: notify.mobile_app
        data:
          message: "⚠️ Plus de 3h d'écran aujourd'hui !"
```

### Déverrouillage automatique le week-end
```yaml
automation:
  - alias: "Déverrouiller le week-end matin"
    trigger:
      - platform: time
        at: "09:00:00"
    condition:
      - condition: time
        weekday: [sat, sun]
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.telephone_enfant
```

## 📦 Installation

### Ce qu'il vous faut
- **Un client VNC** (TightVNC, RealVNC, VNC Viewer...)
- **Home Assistant OS ou Supervised** (pas Container/Core)
- **Un compte Google Family Link** avec au moins un enfant

### Installation HACS
1. Ajoutez ce repo dans HACS en source custom
2. Installez l'add-on **Family Link Auth** depuis le Store
3. Lancez l'add-on
4. **Connectez-vous via VNC** (voir "Comment se connecter" plus haut)
5. Installez l'intégration **Google Family Link** via HACS
6. Configurez dans **Paramètres** → **Appareils et services**

[Guide complet d'installation ici](https://github.com/noiwid/HAFamilyLink/blob/main/INSTALL.md)

## 🚨 Petit disclaimer

Cette intégration utilise des **API non officielles** de Google Family Link (reverse engineering).

⚠️ **À utiliser à vos risques** : ça peut potentiellement enfreindre les CGU de Google. Aucune affiliation avec Google, c'est du bricolage maison !

## 🔗 Liens

- **GitHub** : https://github.com/noiwid/HAFamilyLink
- **Reporter un bug** : https://github.com/noiwid/HAFamilyLink/issues
- **Proposer une feature** : https://github.com/noiwid/HAFamilyLink/issues/new
- **Discussions** : https://github.com/noiwid/HAFamilyLink/discussions

## 🎉 Version actuelle

**v0.5.0** - Synchro temps réel du verrouillage

## 🤝 Contribuer

N'hésitez pas à :
- Reporter des bugs
- Proposer des features
- Faire des PR
- Partager vos automatisations !

---

Voilà, j'espère que ça vous sera utile ! Si vous avez des questions ou des retours, n'hésitez pas.

Bon contrôle parental ! 👨‍👩‍👧‍👦

*Développé par [@noiwid](https://github.com/noiwid) avec l'assistance de Claude*

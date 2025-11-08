# 📱 Google Family Link pour Home Assistant - Contrôlez et surveillez les appareils de vos enfants

Bonjour à tous ! 👋

Je suis ravi de vous présenter mon intégration **Google Family Link pour Home Assistant**, un projet qui me tenait à cœur depuis longtemps.

## 🙏 Remerciements

Avant tout, je tiens à remercier :
- **La communauté Home Assistant** pour l'inspiration et les nombreux exemples d'intégrations
- **L'équipe Playwright** pour leur excellent framework d'automation de navigateur
- **Claude (Anthropic)** qui m'a accompagné dans le développement et la résolution de nombreux défis techniques
- **Tous ceux qui ont partagé leurs connaissances** sur le reverse engineering d'APIs

Sans ces briques, ce projet n'aurait jamais vu le jour !

---

## 🎯 Qu'est-ce que c'est ?

Cette intégration vous permet de **surveiller et contrôler les appareils Google Family Link** de vos enfants directement depuis Home Assistant. Temps d'écran, verrouillage à distance, statistiques d'utilisation... tout est désormais accessible et automatisable !

## ✨ Fonctionnalités principales

### 🔐 Contrôle des appareils
- **Verrouillage/déverrouillage à distance** via des interrupteurs (switches)
- **Synchronisation bidirectionnelle** : les changements faits dans l'app Family Link se reflètent dans Home Assistant
- **Support multi-appareils** : gérez tous les appareils supervisés de vos enfants

### 📊 Suivi du temps d'écran
- **Temps d'écran quotidien** en temps réel
- **Top 10 des applications** les plus utilisées avec statistiques détaillées
- **Répartition par application** (heures, minutes, secondes)
- **Mises à jour automatiques** toutes les 5 minutes (personnalisable)

### 📲 Gestion des applications
- **Nombre d'applications installées**
- **Applications bloquées** avec liste complète
- **Applications avec limites de temps**
- **Détails complets** : noms de package, titres, limites configurées

### 👶 Informations sur l'enfant
- **Profil complet** : nom, email, date de naissance, tranche d'âge
- **Informations des appareils** : modèle, nom, capacités, dernière activité
- **Membres de la famille** avec leurs rôles

## 🏗️ Architecture : Add-on + Intégration

Le projet se compose de **deux éléments complémentaires** :

### 1. **Add-on d'authentification** (obligatoire)
Fournit l'authentification sécurisée via navigateur :
- Automation Playwright avec Chromium headless
- **Serveur VNC intégré** (port 5900) pour interagir avec le navigateur
- Support 2FA (SMS, authenticateur, notifications push)
- Stockage chiffré des cookies
- Rafraîchissement automatique des sessions

### 2. **Intégration Home Assistant**
Assure la surveillance et le contrôle :
- Interface de configuration conviviale (config flow)
- Client API pour communiquer avec Google Family Link
- Coordinateur de données avec cache
- Entités (capteurs et interrupteurs)

**Pourquoi deux composants ?** L'environnement Docker de Home Assistant restreint l'automation de navigateur. L'add-on tourne dans un conteneur séparé avec Chromium et Playwright, tandis que l'intégration gère la récupération de données et le contrôle des appareils.

## 🔐 Processus d'authentification

L'authentification nécessite l'utilisation d'un **client VNC** (comme TightVNC, RealVNC, ou VNC Viewer) :

1. **Démarrer l'add-on** Family Link Auth
2. **Ouvrir l'interface web** (http://[IP_HA]:8099)
3. **Cliquer sur** "Démarrer l'authentification"
4. **Se connecter via VNC** :
   - **Adresse** : `[IP_HA]:5900`
   - **Mot de passe** : `familylink`
5. **Fenêtre Chromium** s'ouvre dans VNC
6. **Se connecter à Google** dans la fenêtre VNC :
   - Entrer votre email Google
   - Entrer votre mot de passe
   - Compléter la 2FA si activée
7. **Les cookies sont automatiquement sauvegardés** ✅

**Pourquoi VNC ?** Le navigateur Chromium tourne dans le conteneur Docker de l'add-on. VNC permet d'y accéder à distance pour compléter le login Google de manière interactive.

**Clients VNC recommandés :**
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

### Prérequis
- **Client VNC** installé sur votre ordinateur/téléphone (TightVNC, RealVNC, VNC Viewer...)
- **Home Assistant OS ou Supervised** (add-ons requis)
- **Compte Google Family Link** actif avec au moins un enfant supervisé

### Via HACS (recommandé)
1. Ajoutez ce dépôt comme source personnalisée dans HACS
2. Installez l'add-on **Family Link Auth** depuis le Store de Supervisor
3. Démarrez l'add-on
4. **Authentifiez-vous via VNC** (voir section "Processus d'authentification" ci-dessus)
5. Installez l'intégration **Google Family Link** via HACS
6. Configurez l'intégration dans **Paramètres** → **Appareils et services**

[Guide d'installation détaillé disponible dans le README](https://github.com/noiwid/HAFamilyLink/blob/main/INSTALL.md)

## 🚨 Avertissement important

Cette intégration utilise des **endpoints non officiels** de l'API Google Family Link obtenus par reverse engineering.

⚠️ **Utilisez-la à vos propres risques**. Cela peut violer les conditions d'utilisation de Google et pourrait entraîner une suspension de compte. Ce projet n'est pas affilié, approuvé ou connecté à Google LLC.

## 🔗 Liens utiles

- **GitHub** : https://github.com/noiwid/HAFamilyLink
- **Signaler un bug** : https://github.com/noiwid/HAFamilyLink/issues
- **Demande de fonctionnalité** : https://github.com/noiwid/HAFamilyLink/issues/new
- **Discussions** : https://github.com/noiwid/HAFamilyLink/discussions

## 🎉 Version actuelle

**v0.5.0** - Synchronisation en temps réel de l'état de verrouillage des appareils

## 🤝 Contributions

Les contributions sont les bienvenues ! N'hésitez pas à :
- Signaler des bugs
- Proposer de nouvelles fonctionnalités
- Soumettre des pull requests
- Partager vos automatisations

---

J'espère que cette intégration vous sera utile ! N'hésitez pas à me faire part de vos retours, suggestions ou questions.

Bon contrôle parental à tous ! 👨‍👩‍👧‍👦

*Développé par [@noiwid](https://github.com/noiwid) avec l'assistance de Claude*

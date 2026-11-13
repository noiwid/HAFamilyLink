/*
 * Google Family Link - dashboard card (custom:familylink-card), served by the integration.
 *
 *   type: custom:familylink-card
 *   device: <device id>              # the phone or tablet (the visual editor offers the list)
 *   entity: switch.alex_phone        # or any Family Link entity of the device
 *   title: Phone                     # optional
 *   compact: true                    # optional: header and bonus bar only (a second device of the child)
 *   bonus: true                      # optional, true by default (written in a new card): false hides the bonus bar (+15 / +30 / +60 buttons)
 *   inline_app_editor: true          # optional: edit apps inside this card (useful in popup containers)
 *   language: en                     # optional: en, fr or pl, else the language of Home Assistant
 *   entities:                        # optional: replace an entity of a role, e.g. a school button of your own
 *     child: { school_time: automation.my_school_mode }
 *
 * The integration tells the card which entities belong to the child and to the device
 * (websocket "familylink/card_entities"), by role: the end of their unique id.
 * Dialogs keep their draft in the card and call the integration's services themselves,
 * so the card needs no helper and no script. Plain custom element: no build, no dependency.
 */
const STR = {
	en: {
		today: 'Today', installed: 'installed', limited: 'limited', blocked: 'blocked', apps: 'Applications', week: 'Weekly limits',
		no_usage: 'No usage today', no_app: 'No app', unlimited: 'Unlimited', per_day: ' / day', allowed: 'Allowed hours: {a} — {b}',
		app: 'Application', cur_blocked: 'Currently blocked', cur_always: 'Currently always allowed',
		cur_limited: 'Currently limited to {t} per day', cur_none: 'Currently no limit of its own',
		always: 'Always allowed', always_sub: 'Even when screen time has run out', none: 'No limit', none_sub: 'Only the overall screen time applies',
		limit: 'Limited', limit_sub: 'Per day', block: 'Blocked', block_sub: 'Can no longer be opened',
		reset: 'Reset', no_bonus: 'No bonus', bonus_on: 'Bonus +{t}', tip_reset: 'Cancel the active bonus', tip_add: '{n} min bonus today',
		tip_custom: 'Bonus of a custom duration', bonus: 'Bonus', bonus_min: 'Bonus minutes', bonus_sub: "Added to today's limit",
		daily_limit: 'Daily limit', bedtime: 'Bedtime', school: 'School', day_settings: 'Day settings', limit_day: 'Screen time allowed that day',
		bed_from: 'Bedtime from', bed_to: 'Bedtime until', steps: 'In 15 min steps', school_from: 'School from', school_to: 'School until',
		pick_device: 'Choose a phone or tablet, not the child.',
		pause: 'Paused', pause_sub: 'Stays installed, resumes with its previous rule', cur_paused: 'Currently paused',
		web: 'Web', web_hint: "Chrome on all of the child's devices", f_approved: 'Only approved sites', f_filtered: 'Try to block explicit sites',
		site_ph: 'example.com', allow: 'Allow', deny: 'Block', approved: 'Approved sites', blocked_sites: 'Blocked sites', no_site: 'None',
		remove: 'Remove', sites: 'Websites', add_site: 'Add a website', several: 'One domain, or several separated by spaces',
		s_allow: 'Always allowed', s_allow_sub: 'Even when the web filter would block it', s_block: 'Always blocked', s_block_sub: 'Chrome will refuse to open it',
		s_remove: 'Remove from the lists', s_remove_sub: 'The web filter decides again', allowed_tag: 'allowed', blocked_tag: 'blocked',
		lock: 'Lock', unlock: 'Unlock', lock_q: 'Lock {d}?', unlock_q: 'Unlock {d}?',
		next_tr: (s) => s,
		settings: 'Settings', strict: 'Strict mode', strict_sub: 'What is changed on the Google side is put back as in Home Assistant',
		unl: 'Unlimited apps during bedtime', unl_sub: 'Off: the apps with unlimited time are blocked too', calls: 'Calls and texts',
		calls_opts: { 'Anyone': 'Anyone', 'Only contacts I add': 'Only contacts I add', 'Contacts I add & limited groups': 'Contacts I add and limited groups' },
		configure: 'Configure the integration', configure_sub: 'Users allowed, strict mode rules, location',
		not_confirmed: 'The start is saved, the end is not: Google has not confirmed it yet. Try again.',
		ring: 'Ring', ring_q: 'Ring {d}?', ring_sub: 'The device rings so it can be found.',
		locked_by: 'Locked: {r}',
		why: { manually_locked: 'Locked', bedtime_active: 'Locked: bedtime', school_time_active: 'Locked: school time', daily_limit_reached: 'Locked: daily limit reached' },
		lock_sub: 'The device can no longer be used until it is unlocked.', unlock_sub: 'The device can be used again, within its limits.',
		save: 'Save', saving: 'Saving…', close: 'Close', loading: 'Loading…', not_found: 'Family Link entity not found: ',
		days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
	},
	fr: {
		today: 'Jour', installed: 'installées', limited: 'limitées', blocked: 'bloquées', apps: 'Applications', week: 'Limites de la semaine',
		no_usage: "Aucune utilisation aujourd'hui", no_app: 'Aucune application', unlimited: 'Illimitée', per_day: ' / jour',
		allowed: 'Plage autorisée : {a} — {b}',
		app: 'Application', cur_blocked: 'Actuellement bloquée', cur_always: 'Actuellement toujours autorisée',
		cur_limited: 'Actuellement limitée à {t} par jour', cur_none: 'Actuellement sans limite propre',
		always: 'Toujours autorisée', always_sub: "Même quand le temps d'écran est écoulé", none: 'Sans limite', none_sub: "Seul le temps d'écran global s'applique",
		limit: 'Limitée', limit_sub: 'Par jour', block: 'Bloquée', block_sub: 'Ne peut plus être ouverte',
		reset: 'Reset', no_bonus: 'Aucun bonus', bonus_on: 'Bonus +{t}', tip_reset: 'Annuler le bonus en cours', tip_add: "Bonus de {n} min aujourd'hui",
		tip_custom: "Bonus d'une durée au choix", bonus: 'Bonus', bonus_min: 'Minutes de bonus', bonus_sub: "Ajoutées à la limite d'aujourd'hui",
		daily_limit: 'Limite du jour', bedtime: 'Coucher', school: 'École', day_settings: 'Réglage du jour', limit_day: "Temps d'écran autorisé ce jour-là",
		bed_from: 'Coucher à partir de', bed_to: "Coucher jusqu'à", steps: 'Par pas de 15 min', school_from: 'École à partir de', school_to: "École jusqu'à",
		pick_device: "Choisissez un téléphone ou une tablette, pas l'enfant.",
		pause: 'En pause', pause_sub: "Reste installée, reprend avec sa règle d'avant", cur_paused: 'Actuellement en pause',
		web: 'Web', web_hint: "Chrome sur tous les appareils de l'enfant", f_approved: 'Sites approuvés seulement', f_filtered: 'Bloquer les sites explicites',
		site_ph: 'exemple.fr', allow: 'Autoriser', deny: 'Bloquer', approved: 'Sites autorisés', blocked_sites: 'Sites bloqués', no_site: 'Aucun',
		remove: 'Retirer', sites: 'Sites web', add_site: 'Ajouter un site', several: 'Un domaine, ou plusieurs séparés par des espaces',
		s_allow: 'Toujours autorisé', s_allow_sub: 'Même si le filtre web le bloquerait', s_block: 'Toujours bloqué', s_block_sub: 'Chrome refusera de l\'ouvrir',
		s_remove: 'Retirer des listes', s_remove_sub: 'Le filtre web décide de nouveau', allowed_tag: 'autorisé', blocked_tag: 'bloqué',
		lock: 'Verrouiller', unlock: 'Déverrouiller', lock_q: 'Verrouiller {d} ?', unlock_q: 'Déverrouiller {d} ?',
		next_tr: (s) => s.replace('Daily limit soon reached', 'Limite du jour bientôt atteinte').replace('No restrictions', 'Aucune restriction')
			.replace('School time', 'École').replace('Bedtime', 'Coucher').replace('(ends ', '(fin ').replace(/\bat (\d)/, 'à $1').replace('tomorrow', 'demain')
			.replace(/\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b/, (d) => ({ Mon: 'lun.', Tue: 'mar.', Wed: 'mer.', Thu: 'jeu.', Fri: 'ven.', Sat: 'sam.', Sun: 'dim.' })[d]),
		settings: 'Réglages', strict: 'Mode strict', strict_sub: 'Ce qui est changé côté Google est remis comme dans Home Assistant',
		unl: 'Apps illimitées pendant le coucher', unl_sub: 'Désactivé : les apps à temps illimité sont bloquées aussi', calls: 'Appels et SMS',
		calls_opts: { 'Anyone': 'Tout le monde', 'Only contacts I add': 'Seulement mes contacts ajoutés', 'Contacts I add & limited groups': 'Mes contacts ajoutés et groupes limités' },
		configure: "Configurer l'intégration", configure_sub: 'Utilisateurs autorisés, règles du mode strict, position',
		not_confirmed: "Le début est enregistré, pas la fin : Google ne l'a pas encore confirmé. Réessayez.",
		ring: 'Faire sonner', ring_q: 'Faire sonner {d} ?', ring_sub: "L'appareil sonne pour qu'on le retrouve.",
		locked_by: 'Bloqué : {r}',
		why: { manually_locked: 'Verrouillé', bedtime_active: 'Bloqué : coucher', school_time_active: 'Bloqué : école', daily_limit_reached: 'Bloqué : limite du jour atteinte' },
		lock_sub: "L'appareil ne peut plus être utilisé jusqu'à son déverrouillage.", unlock_sub: "L'appareil peut de nouveau être utilisé, dans ses limites.",
		save: 'Enregistrer', saving: 'Enregistrement…', close: 'Fermer', loading: 'Chargement…', not_found: 'Entité Family Link introuvable : ',
		days: ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'],
	},
};
STR.pl = {
    today: 'Dzisiaj', installed: 'Zainstalowane', limited: 'Z limitami', blocked: 'Zablokowane', apps: 'Aplikacje', week: 'Limity tygodniowe',
    no_usage: 'Brak aktywności dzisiaj', no_app: 'Brak aplikacji', unlimited: 'Bez limitu', per_day: ' / dzień', allowed: 'Dozwolone godziny: {a} — {b}',
    app: 'Aplikacja', cur_blocked: 'Obecnie zablokowana', cur_always: 'Obecnie zawsze dozwolona',
    cur_limited: 'Obecnie limit {t} dziennie', cur_none: 'Obecnie bez osobnego limitu',
    always: 'Zawsze dozwolona', always_sub: 'Dostępna nawet po wyczerpaniu czasu ekranowego',
    none: 'Bez osobnego limitu', none_sub: 'Obowiązuje tylko ogólny limit czasu ekranowego',
    limit: 'Z limitem', limit_sub: 'Dziennie', block: 'Zablokowana', block_sub: 'Nie można jej uruchomić',
    reset: 'Resetuj', no_bonus: 'Brak dodatkowego czasu', bonus_on: 'Dodatkowy czas +{t}',
    tip_reset: 'Anuluj dodatkowy czas', tip_add: 'Dodaj dziś {n} min',
    tip_custom: 'Dodaj dowolną liczbę minut', bonus: 'Dodatkowy czas', bonus_min: 'Liczba minut', bonus_sub: 'Dodawane do dzisiejszego limitu',
    daily_limit: 'Dzienny limit', bedtime: 'Pora snu', school: 'Szkoła', day_settings: 'Ustawienia dnia',
    limit_day: 'Dozwolony czas ekranowy tego dnia', bed_from: 'Pora snu od', bed_to: 'Pora snu do',
    steps: 'Co 15 minut', school_from: 'Zajęcia od', school_to: 'Zajęcia do',
    pick_device: 'Wybierz telefon lub tablet, a nie profil dziecka.',
    pause: 'Wstrzymana', pause_sub: 'Pozostaje zainstalowana; później wróci do poprzednich ustawień', cur_paused: 'Obecnie wstrzymana',
    web: 'Internet', web_hint: 'Chrome na wszystkich urządzeniach dziecka',
    f_approved: 'Tylko zatwierdzone witryny', f_filtered: 'Próbuj blokować strony dla dorosłych',
    site_ph: 'example.com', allow: 'Zezwól', deny: 'Zablokuj', approved: 'Zatwierdzone witryny', blocked_sites: 'Zablokowane witryny', no_site: 'Brak',
    remove: 'Usuń', sites: 'Witryny', add_site: 'Dodaj witrynę', several: 'Jedna domena lub kilka oddzielonych spacją',
    s_allow: 'Zawsze dozwolona', s_allow_sub: 'Otwierana nawet wtedy, gdy filtr ją blokuje',
    s_block: 'Zawsze zablokowana', s_block_sub: 'Chrome nie otworzy tej witryny',
    s_remove: 'Usuń z list', s_remove_sub: 'Dalszy dostęp określa filtr', allowed_tag: 'dozwolona', blocked_tag: 'zablokowana',
    lock: 'Zablokuj', unlock: 'Odblokuj', lock_q: 'Zablokować {d}?', unlock_q: 'Odblokować {d}?',
    next_tr: (s) => String(s ?? '')
        .replace('Daily limit soon reached', 'Dzienny limit wkrótce się skończy')
        .replace('No restrictions', 'Brak ograniczeń')
        .replace('School time', 'Zajęcia szkolne')
        .replace('Bedtime', 'Pora snu')
        .replace('(ends ', '(koniec ')
        .replace(/\bat (\d)/, 'o $1')
        .replace('tomorrow', 'jutro')
        .replace(/\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b/g, (d) => ({Mon:'pon.',Tue:'wt.',Wed:'śr.',Thu:'czw.',Fri:'pt.',Sat:'sob.',Sun:'niedz.'})[d]),
    settings: 'Ustawienia', strict: 'Tryb ścisły',
    strict_sub: 'Zmiany dokonane w Google są przywracane do ustawień Home Assistanta',
    unl: 'Aplikacje bez limitu podczas pory snu', unl_sub: 'Wyłączone: także aplikacje bez limitu są wtedy blokowane',
    calls: 'Połączenia i SMS-y',
    calls_opts: {'Anyone': 'Wszyscy', 'Only contacts I add': 'Tylko dodane kontakty', 'Contacts I add & limited groups': 'Dodane kontakty i wybrane grupy'},
    configure: 'Konfiguruj integrację', configure_sub: 'Uprawnieni użytkownicy, zasady trybu ścisłego i lokalizacja',
    not_confirmed: 'Początek zapisano, ale Google nie potwierdził końca. Spróbuj ponownie.',
    ring: 'Zadzwoń', ring_q: 'Uruchomić dzwonek na {d}?', ring_sub: 'Telefon zacznie dzwonić, aby łatwiej go znaleźć.',
    why: {manually_locked: 'Zablokowany', bedtime_active: 'Zablokowany: pora snu', school_time_active: 'Zablokowany: szkoła', daily_limit_reached: 'Zablokowany: wyczerpany limit'},
    lock_sub: 'Nie będzie można korzystać z urządzenia do czasu odblokowania.',
    unlock_sub: 'Można ponownie korzystać z urządzenia w ramach obowiązujących limitów.',
    save: 'Zapisz', saving: 'Zapisywanie…', close: 'Zamknij', loading: 'Wczytywanie…', not_found: 'Nie znaleziono encji Family Link: ',
    days: ['Poniedziałek','Wtorek','Środa','Czwartek','Piątek','Sobota','Niedziela'],
};

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const hm = (m) => { m = Math.round(m); const h = Math.floor(m / 60); return h ? `${h} h ${String(m % 60).padStart(2, '0')}` : `${m} min`; };
const hShort = (m) => { m = Math.round(m); const h = Math.floor(m / 60), r = m % 60; return h ? `${h}h${r ? String(r).padStart(2, '0') : ''}` : `${r}min`; };
const hour = (m) => `${Math.floor(m / 60)}h${m % 60 ? String(m % 60).padStart(2, '0') : ''}`;  // a time of day: 0h, 22h30
const clock = (m) => `${String(Math.floor(m / 60)).padStart(2, '0')}h${String(m % 60).padStart(2, '0')}`;
const toMin = (s) => { const p = String(s || '').split(':'); return p.length >= 2 ? Number(p[0]) * 60 + Number(p[1]) : NaN; };
const short = (name) => String(name).split(/[:\-–]/)[0].trim() || String(name);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
// weekdays are numbered as in the unique ids: 1 = Monday
const entityOfDevice = (hass, device) => device && Object.values(hass.entities || {}).find((e) => e.device_id === device && e.platform === 'familylink')?.entity_id;
const deviceOfEntity = (hass, entity) => entity && hass.entities?.[entity]?.device_id;
const todayNum = () => ((new Date().getDay() + 6) % 7) + 1;

class FamilyLinkCard extends HTMLElement {
	setConfig(config) {
		if (!config || (!config.device && !config.entity && !config.entities)) throw new Error('familylink-card: choose the device (phone or tablet)');
		this._config = config;
		this._tab = 'today';
		this._seen = '';
		this._map = null;
		this._resolving = null;  // a new device: look it up again
		if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
		if (!this._resize) { this._resize = new ResizeObserver(() => this._fitTabs()); this._resize.observe(this); }
	}

	static getStubConfig(hass) {
		// the child is found from the device: each device belongs to one child
		const sw = Object.keys(hass.states).find((id) => id.startsWith('switch.') && hass.entities?.[id]?.platform === 'familylink' && 'locked' in hass.states[id].attributes);
		// bonus is true by default: written in the config of a new card, so the option is there to see (false hides the bonus bar)
		return { device: (sw && hass.entities[sw].device_id) || '', bonus: true };
	}

	static getConfigElement() { return document.createElement('familylink-card-editor'); }

	getCardSize() { return this._config && this._config.compact ? 3 : 10; }
	// sections view: full width by default, can be narrowed to half; the height follows the content
	getGridOptions() { return { columns: 12, min_columns: 6, rows: 'auto' }; }

	set hass(hass) {
		this._hass = hass;
		if (!this._map) return this._resolve();
		const seen = this._watched().map((id) => (hass.states[id] ? hass.states[id].last_updated : 'x')).join('|') + hass.language;
		if (seen === this._seen) return;
		this._seen = seen;
		this._render();
	}

	_resolve() {
		if (this._resolving) return;
		const over = this._config.entities || {};
		const done = (found) => {
			if (!found.device_id && !this._config.entities) {  // the child's own device was picked, not a phone or tablet
				// _resolving stays set: the message stays until the config changes, no new lookup per state change
				return this._shell(`<div class="msg err">${this._t('pick_device')}</div>`);
			}
			this._map = { child: { ...(found.child || {}), ...(over.child || {}) }, device: { ...(found.device || {}), ...(over.device || {}) } };
			this._resolving = null;
			this._seen = '';
			this.hass = this._hass;
		};
		const entity = this._config.entity || entityOfDevice(this._hass, this._config.device);
		if (!entity) {
			if (this._config.entities) return done({});
			return this._shell(`<div class="msg err">${this._t('not_found')}${esc(this._config.device || '')}</div>`);
		}
		this._shell(`<div class="msg">${this._t('loading')}</div>`);
		this._resolving = this._hass.callWS({ type: 'familylink/card_entities', entity_id: entity })
			.then(done)
			.catch(() => {
				if (this._config.entities) return done({});
				this._shell(`<div class="msg err">${this._t('not_found')}${esc(entity)}</div>`);
				// Home Assistant restarting with the dashboard open: look it up again a little later
				setTimeout(() => { this._resolving = null; if (this._hass) this.hass = this._hass; }, 30000);
			});
	}

	_watched() { return [...Object.values(this._map.child), ...Object.values(this._map.device)]; }
	_t(key) { return (STR[(this._config.language || this._hass.language || 'en').slice(0, 2)] || STR.en)[key] ?? STR.en[key]; }
	_c(role) { return this._hass.states[this._map.child[role]]; }
	_d(role) { return this._hass.states[this._map.device[role]]; }
	_n(st) { return st ? parseFloat(st.state) : NaN; }
	_apps(st) { return (st && st.attributes.apps) || []; }
	_on(st) { return !!st && st.state !== 'unavailable' && st.state !== 'unknown'; }
	_shell(body) { this.shadowRoot.innerHTML = `<style>${FamilyLinkCard.css}</style><ha-card>${body}</ha-card>`; }

	_call(domain, service, data) { return this._hass.callService(domain, service, data); }

	/** Every app of the child with its rule: block / always / limit (minutes) / none. */
	_rules() {
		const rules = new Map();
		const put = (st, rule) => this._apps(st).forEach((a) => rules.set(a.package, { name: a.name, package: a.package, ...rule(a) }));
		put(this._c('apps_without_limits'), () => ({ mode: 'none' }));
		put(this._c('always_allowed_apps'), () => ({ mode: 'always' }));
		put(this._c('apps_with_limits'), (a) => (a.limit_minutes === -2 ? { mode: 'always' } : a.limit_minutes === 1 ? { mode: 'pause', minutes: 1 } : { mode: 'limit', minutes: a.limit_minutes }));  // pause_app sets a 1 min limit
		put(this._c('blocked_apps'), () => ({ mode: 'block' }));
		return rules;
	}

	_render() {
		// Do not discard the app editor or its unsaved draft during state updates.
		if (this._inlineAppDialog?.isConnected) return;
		const t = (k) => this._t(k), cfg = this._config;
		const lock = this._d('lock'), locked = lock && lock.state === 'off';
		const used = this._n(this._d('daily_screen_time')), limit = this._n(this._d('daily_limit')), bonus = this._n(this._d('active_bonus')) || 0;
		// daily limit off: no "/ limit" and no bar, whatever quota the device still reports
		const limitOn = (this._c('daily_limit') || {}).state !== 'off';
		const total = limitOn && limit > 0 ? limit + bonus : NaN, pct = total > 0 ? Math.min(100, (used / total) * 100) : 0;
		const battery = this._n(this._d('battery_level'));
		const base = cfg.icon || (/tab|pad/i.test((lock && (lock.attributes.model || lock.attributes.friendly_name)) || '') ? 'mdi:tablet' : 'mdi:cellphone');
		const icon = locked && base === 'mdi:cellphone' ? 'mdi:cellphone-lock' : base;
		const day = todayNum();
		const bedStart = toMin((this._c(`bedtime_${day}_start`) || {}).state), bedEnd = toMin((this._c(`bedtime_${day}_end`) || {}).state);
		// bedtime off today: no allowed hours to show
		const bedOn = (this._c('bedtime') || {}).state !== 'off';
		const window = bedOn && !isNaN(bedStart) && !isNaN(bedEnd) ? t('allowed').replace('{a}', hour(bedEnd)).replace('{b}', hour(bedStart)) : '';
		const next = this._d('next_restriction');
		// a lock of your own (homework...) named by the entity that is on: lock_reasons: { input_boolean.homework: Homework }
		const own = locked && lock.attributes.restriction_reason === 'manually_locked'
			&& Object.entries(cfg.lock_reasons || {}).find(([id]) => (this._hass.states[id] || {}).state === 'on');
		const status = own ? t('locked_by').replace('{r}', own[1]) : locked ? (t('why') || {})[lock.attributes.restriction_reason] || ''
			: next && !['unknown', 'unavailable', '', 'No restrictions'].includes(next.state) ? t('next_tr')(next.state) : '';  // the sensor writes fixed English sentences
		const reset = this._d('reset_bonus');
		const press = (role, n, tip) => (this._d(role) ? `<button class="round" data-press="${role}" data-tip="${esc(tip)}"><ha-icon icon="mdi:fast-forward-${n}"></ha-icon></button>` : '');
		let html = `
			<div class="head">
				${lock ? `<button class="lockbtn" data-lock data-tip="${esc(locked ? t('unlock') : t('lock'))}" aria-label="${esc(locked ? t('unlock') : t('lock'))}"><ha-icon icon="${icon}" style="color:var(${locked ? '--error-color' : '--success-color'})"></ha-icon></button>` : `<ha-icon icon="${icon}"></ha-icon>`}
				<span class="title">${esc(cfg.title || (lock && lock.attributes.friendly_name) || '')}</span>
				${isNaN(battery) ? '' : `<span class="battery"><ha-icon icon="mdi:battery"></ha-icon>${Math.round(battery)}%</span>`}
				${this._d('ring') && this._d('ring').state !== 'unavailable' ? `<button class="ringbtn" data-ring data-tip="${esc(t('ring'))}" aria-label="${esc(t('ring'))}"><ha-icon icon="mdi:bell-ring-outline"></ha-icon></button>` : ''}
				<span class="used">${isNaN(used) ? '' : hm(used)}${isNaN(total) ? '' : ' / ' + hm(total)}${bonus > 0 ? ` <span class="plus">(+${hm(bonus)})</span>` : ''}</span>
				<button class="ringbtn gear" data-settings data-tip="${esc(t('settings'))}" aria-label="${esc(t('settings'))}"><ha-icon icon="mdi:cog-outline"></ha-icon></button>
			</div>
			${isNaN(total) ? '' : `<div class="track big"><div style="width:${pct}%"></div></div>`}
			${window || status ? `<div class="window">${esc(window)}${window && status ? ' · ' : ''}${status ? `<span class="${locked ? 'why' : ''}">${esc(status)}</span>` : ''}</div>` : ''}
			${cfg.bonus === false ? '' : `<div class="bonus">
				<button class="round big" data-press="reset_bonus" data-tip="${esc(t('tip_reset'))}" ${this._on(reset) ? '' : 'disabled'}><ha-icon icon="mdi:restart"></ha-icon></button>
				<div class="btxt"><div>${t('reset')}</div><small>${bonus > 0 ? t('bonus_on').replace('{t}', hm(bonus)) : t('no_bonus')}</small></div>
				${press('bonus_15min', 15, t('tip_add').replace('{n}', 15))}${press('bonus_30min', 30, t('tip_add').replace('{n}', 30))}${press('bonus_60min', 60, t('tip_add').replace('{n}', 60))}
				<button class="round" data-dialog="bonus" data-tip="${esc(t('tip_custom'))}"><ha-icon icon="mdi:timer-edit-outline"></ha-icon></button>
			</div>`}`;
		if (!cfg.compact) html += this._childPart();
		this._shell(html);
		this._fitTabs();
		// icons and fonts arrive after the first layout (slower on a phone) and widen the tabs: measure again
		for (const ms of [300, 1500]) setTimeout(() => this._fitTabs(), ms);
		const root = this.shadowRoot;
		root.querySelectorAll('[data-level]').forEach((b) => b.addEventListener('click', () => {
			if (!this._busy && (this._c('web_filter') || {}).state !== b.dataset.level) this._web('select_option', { option: b.dataset.level });
		}));
		root.querySelectorAll('[data-site]').forEach((r) => r.addEventListener('click', () => this._siteDialog(r.dataset.site, r.dataset.kind)));
		const addSite = root.querySelector('[data-add-site]');
		if (addSite) addSite.addEventListener('click', () => this._siteDialog('', ''));
		root.querySelectorAll('[data-press]').forEach((b) => b.addEventListener('click', () => this._call('button', 'press', { entity_id: this._map.device[b.dataset.press] })));
		root.querySelectorAll('[data-toggle]').forEach((b) => b.addEventListener('click', () => this._call('homeassistant', 'toggle', { entity_id: this._map.child[b.dataset.toggle] })));
		root.querySelectorAll('[data-tab]').forEach((b) => b.addEventListener('click', () => { this._tab = b.dataset.tab; this._render(); }));
		root.querySelectorAll('[data-pkg]').forEach((r) => r.addEventListener('click', () => { const rule = this._rules().get(r.dataset.pkg); if (rule) this._appDialog(rule); }));
		root.querySelectorAll('[data-day]').forEach((c) => c.addEventListener('click', () => this._dayDialog(c.dataset.day)));
		const bonusBtn = root.querySelector('[data-dialog="bonus"]');
		if (bonusBtn) bonusBtn.addEventListener('click', () => this._bonusDialog());
		const lockBtn = root.querySelector('[data-lock]');
		if (lockBtn) lockBtn.addEventListener('click', () => this._lockDialog());
		root.querySelector('[data-settings]').addEventListener('click', () => this._settingsDialog());
		const ringBtn = root.querySelector('[data-ring]');
		if (ringBtn) ringBtn.addEventListener('click', () => this._open({
			title: t('ring'), icon: 'mdi:bell-ring-outline', name: t('ring_q').replace('{d}', cfg.title || (lock && lock.attributes.friendly_name) || ''), sub: t('ring_sub'),
			state: {}, fields: [], saveLabel: t('ring'), saveIcon: 'mdi:bell-ring-outline',
			save: () => this._call('button', 'press', { entity_id: this._map.device.ring }),
		}));
	}

	/** Locking is never one tap away: on a phone a scroll can land on the icon. */
	_settingsDialog() {
		const t = (k) => this._t(k), strict = this._c('strict_mode'), unl = this._c('downtime_unlimited_apps'), calls = this._c('allowed_calls_texts');
		const fields = [], state = {};
		if (this._on(strict)) { state.strict = strict.state === 'on'; fields.push({ key: 'strict', toggle: true, icon: 'mdi:shield-lock-outline', title: t('strict'), sub: t('strict_sub') }); }
		// unknown until the setting is first changed: shown off, as Google behaves
		if (unl && unl.state !== 'unavailable') { state.unl = unl.state === 'on'; fields.push({ key: 'unl', toggle: true, icon: 'mdi:infinity', title: t('unl'), sub: t('unl_sub') }); }
		if (this._on(calls)) {
			state.calls = calls.state;
			fields.push({ label: t('calls') });
			for (const o of calls.attributes.options || []) fields.push({ key: 'calls', value: o, icon: 'mdi:phone-outline', title: t('calls_opts')[o] || o, sub: '' });
		}
		// the options flow is for administrators only
		if (this._hass.user && this._hass.user.is_admin) fields.push({ href: '/config/integrations/integration/familylink', icon: 'mdi:cog-outline', title: t('configure'), sub: t('configure_sub') });
		const child = this._map.child, now = { ...state };
		this._open({
			title: t('settings'), icon: 'mdi:cog-outline', name: ((this._c('screen_time_total') || {}).attributes || {}).child_name || '', sub: '',
			state, fields,
			save: async (s) => {
				if (s.strict !== now.strict) await this._call('switch', s.strict ? 'turn_on' : 'turn_off', { entity_id: child.strict_mode });
				if (s.unl !== now.unl) await this._call('switch', s.unl ? 'turn_on' : 'turn_off', { entity_id: child.downtime_unlimited_apps });
				if (s.calls !== now.calls) await this._call('select', 'select_option', { entity_id: child.allowed_calls_texts, option: s.calls });
			},
		});
	}

	_lockDialog() {
		const t = (k) => this._t(k), lock = this._d('lock');
		const locked = lock.state === 'off', name = this._config.title || lock.attributes.friendly_name || '';
		this._open({
			title: locked ? t('unlock') : t('lock'), icon: locked ? 'mdi:lock-open-variant-outline' : 'mdi:lock-outline',
			name: (locked ? t('unlock_q') : t('lock_q')).replace('{d}', name), sub: locked ? t('unlock_sub') : t('lock_sub'),
			state: {}, fields: [], saveLabel: locked ? t('unlock') : t('lock'), saveIcon: locked ? 'mdi:lock-open-variant-outline' : 'mdi:lock-outline',
			// the switch is "on" when the device is usable
			save: () => this._call('switch', locked ? 'turn_on' : 'turn_off', { entity_id: this._map.device.lock }),
		});
	}

	/** Tab words when the five tabs fit with them, icons and counts only when one would be cut. */
	_fitTabs() {
		const tabs = this.shadowRoot && this.shadowRoot.querySelector('.tabs');
		if (!tabs) return;
		// the words go, the icons and counts stay
		// the row as a whole too: tabs do not shrink below their content, the row overflows instead
		const cut = () => tabs.scrollWidth > tabs.clientWidth + 1 || [...tabs.children].some((b) => b.scrollWidth > b.clientWidth + 1);
		tabs.classList.remove('tight');
		// on a phone the words crowd the tabs even when they fit: icons and counts only there
		if (tabs.clientWidth < 405 || cut()) tabs.classList.add('tight');
	}

	_childPart() {
		const t = (k) => this._t(k);
		const toggle = (role, ico, label) => {
			const st = this._c(role);
			if (!this._on(st)) return '';
			return `<button class="tile${st.state === 'on' ? ' on' : ''}" data-toggle="${role}"><ha-icon icon="${ico}"></ha-icon><span>${label}</span></button>`;
		};
		const toggles = toggle('daily_limit', 'mdi:timer-sand', t('daily_limit')) + toggle('bedtime', 'mdi:weather-night', t('bedtime')) + toggle('school_time', 'mdi:school', t('school'));
		const rules = this._rules(), all = [...rules.values()];
		const mark = (r) => ({ always: 'mdi:infinity', block: 'mdi:block-helper', limit: 'mdi:timer-sand', pause: 'mdi:pause-circle-outline' }[r.mode] || '');
		const row = (r, right, bar) => `
			<div class="row" data-pkg="${esc(r.package)}">
				<div class="name"><span>${esc(short(r.name))}</span>${mark(r) ? `<ha-icon icon="${mark(r)}"></ha-icon>` : ''}</div>
				<div class="right">${right}</div>
				${bar === undefined ? '' : `<div class="track"><div style="width:${bar}%"></div></div>`}
			</div>`;
		let list;
		if (this._tab === 'today') {
			const used = this._apps(this._d('daily_screen_time')).slice(0, 7), max = Math.max(1, ...used.map((a) => a.minutes));
			list = used.length ? used.map((a) => row(rules.get(a.package) || { name: a.name, package: a.package, mode: 'none' }, hm(a.minutes), (a.minutes / max) * 100)).join('') : `<div class="empty">${t('no_usage')}</div>`;
		} else if (this._tab === 'web') {
			list = this._webPart();
		} else {
			const pick = { installed: () => true, limited: (r) => r.mode === 'limit' || r.mode === 'pause', blocked: (r) => r.mode === 'block' }[this._tab];
			const rows = all.filter(pick).sort((a, b) => a.name.localeCompare(b.name));
			const right = (r) => (this._tab !== 'limited' ? '' : r.mode === 'pause' ? t('pause') : hm(r.minutes) + t('per_day'));
			list = rows.length ? `<div class="${this._tab === 'limited' ? '' : 'cols'}">${rows.map((r) => row(r, right(r))).join('')}</div>` : `<div class="empty">${t('no_app')}</div>`;
		}
		const tab = (key, ico, count, word) => `<button class="tab${this._tab === key ? ' on' : ''}" data-tab="${key}" title="${esc(`${count} ${word}`.trim())}"><ha-icon icon="${ico}"></ha-icon><span>${count === '' ? '' : count + ' '}<span class="lbl">${word}</span></span></button>`;
		const shortDays = t('days').map((d) => d.slice(0, 3));
		const today = todayNum();
		const week = DAYS.map((_, i) => {
			const day = i + 1;
			const lim = this._c(`daily_limit_${day}`);
			if (!lim) return '';
			const s = toMin((this._c(`bedtime_${day}_start`) || {}).state), e = toMin((this._c(`bedtime_${day}_end`) || {}).state);
			return `<button class="day${day === today ? ' on' : ''}" data-day="${day}"><small>${shortDays[i]}</small><b>${isNaN(this._n(lim)) ? '–' : hShort(this._n(lim))}</b><i>${!isNaN(s) && !isNaN(e) ? `${hour(s)}-${hour(e)}` : ''}</i></button>`;
		}).join('');
		return `
			${toggles ? `<div class="tiles">${toggles}</div>` : ''}
			<div class="label">${t('apps')}</div>
			<div class="tabs">
				${tab('today', 'mdi:clock-outline', '', t('today'))}
				${tab('installed', 'mdi:apps', all.length, t('installed'))}
				${tab('limited', 'mdi:timer-lock-outline', all.filter((r) => r.mode === 'limit' || r.mode === 'pause').length, t('limited'))}
				${tab('blocked', 'mdi:cancel', all.filter((r) => r.mode === 'block').length, t('blocked'))}
				${this._c('web_filter') || this._c('approved_sites') ? tab('web', 'mdi:web', '', t('web')) : ''}
			</div>
			<div class="list">${list}</div>
			${week ? `<div class="label">${t('week')}</div><div class="week">${week}</div>` : ''}`;
	}

	/** Chrome filter level and site lists (Family Link "Google Chrome and Web"), for the whole child. */
	_webPart() {
		const t = (k) => this._t(k), filter = this._c('web_filter');
		const sites = (role) => ((this._c(role) || {}).attributes || {}).sites || [];
		const level = (option, label) => `<button class="pill${filter && filter.state === option ? ' on' : ''}" data-level="${esc(option)}" ${this._busy ? 'disabled' : ''}>${label}</button>`;
		const rows = [...sites('approved_sites').map((x) => [x, 'allow']), ...sites('blocked_sites').map((x) => [x, 'block'])]
			.sort((a, b) => a[0].localeCompare(b[0]))
			.map(([x, kind]) => `<div class="site" data-site="${esc(x)}" data-kind="${kind}"><span>${esc(x)}</span><em class="${kind}">${kind === 'allow' ? t('allowed_tag') : t('blocked_tag')}</em></div>`).join('');
		return `
			${filter ? `<div class="pills">${level('Only approved sites', t('f_approved'))}${level('Try to block explicit sites', t('f_filtered'))}</div>` : ''}
			<div class="hint">${t('web_hint')}</div>
			${this._webError ? `<div class="err">${esc(this._webError)}</div>` : ''}
			<div class="sitehead"><small>${t('sites')}</small><button class="round" data-add-site data-tip="${esc(t('add_site'))}" aria-label="${esc(t('add_site'))}"><ha-icon icon="mdi:plus"></ha-icon></button></div>
			${rows || `<div class="empty left">${t('no_site')}</div>`}`;
	}

	async _web(service, data) {
		this._busy = true; this._webError = ''; this._render();
		try {
			if (service === 'select_option') await this._call('select', 'select_option', { entity_id: this._map.child.web_filter, ...data });
			else await this._call('familylink', service, { entity_id: this._map.child.screen_time_total || this._map.device.lock, ...data });
		} catch (err) {
			this._webError = (err && err.message) || String(err);
		}
		this._busy = false;
		this._render();
	}

	_siteDialog(site, kind) {
		const t = (k) => this._t(k), target = this._map.child.screen_time_total || this._map.device.lock;
		const fields = [
			{ key: 'mode', value: 'allow', icon: 'mdi:check-circle-outline', title: t('s_allow'), sub: t('s_allow_sub') },
			{ key: 'mode', value: 'block', icon: 'mdi:cancel', title: t('s_block'), sub: t('s_block_sub') },
		];
		if (site) fields.push({ key: 'mode', value: 'remove', icon: 'mdi:delete-outline', title: t('s_remove'), sub: t('s_remove_sub') });
		this._open({
			title: site ? t('web') : t('add_site'), icon: 'mdi:web', name: site || t('add_site'), sub: site ? '' : t('several'),
			input: site ? null : { key: 'sites', placeholder: t('site_ph') },
			state: { mode: kind || 'block', sites: '' }, fields,
			save: async (s) => {
				const list = site ? [site] : s.sites.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);
				if (!list.length || (site && s.mode === kind)) return;
				// a site is either approved or blocked: adding it as the other kind replaces it
				const service = { allow: 'allow_site', block: 'block_site', remove: 'remove_site' }[s.mode];
				await this._call('familylink', service, { entity_id: target, sites: list });
			},
		});
	}

	_open(spec) {
		const dialog = document.createElement('familylink-dialog');
		if (spec.inlineInCard) {
			const surface = this.shadowRoot?.querySelector('ha-card');
			if (surface) {
				// Reuse the current card, rather than placing a modal above its parent popup.
				this._inlineAppDialog = dialog;
				dialog._inlineInCard = true;
				const originalClose = dialog._close.bind(dialog);
				dialog._close = () => {
					originalClose();
					this._inlineAppDialog = null;
					if (this.isConnected) this._render();
				};
				surface.replaceChildren(dialog);
				dialog.open({ ...spec, t: (k) => this._t(k) });
				return;
			}
		}
		document.body.appendChild(dialog);
		dialog.open({ ...spec, t: (k) => this._t(k) });
	}

	_appDialog(rule) {
		const t = (k) => this._t(k), target = this._map.child.screen_time_total || this._map.device.lock;
		const current = { block: t('cur_blocked'), always: t('cur_always'), limit: t('cur_limited').replace('{t}', hm(rule.minutes || 0)), none: t('cur_none'), pause: t('cur_paused') }[rule.mode];
		this._open({
			inlineInCard: this._config.inline_app_editor === true,
			title: t('app'), icon: 'mdi:cellphone-cog', name: short(rule.name), sub: current,
			state: { mode: rule.mode, minutes: rule.mode === 'limit' && rule.minutes > 0 ? rule.minutes : 60 },
			fields: [
				{ key: 'mode', value: 'always', icon: 'mdi:infinity', title: t('always'), sub: t('always_sub') },
				{ key: 'mode', value: 'none', icon: 'mdi:check-circle-outline', title: t('none'), sub: t('none_sub') },
				{ key: 'mode', value: 'limit', icon: 'mdi:timer-outline', title: t('limit'), sub: t('limit_sub'), stepper: { key: 'minutes', min: 15, max: 1440, step: 15, fmt: hm } },
				{ key: 'mode', value: 'pause', icon: 'mdi:pause-circle-outline', title: t('pause'), sub: t('pause_sub') },
				{ key: 'mode', value: 'block', icon: 'mdi:cancel', title: t('block'), sub: t('block_sub') },
			],
			save: async (s) => {
				const call = (service, data) => this._call('familylink', service, { entity_id: target, package_name: rule.package, ...data });
				const pause = (service) => this._call('familylink', service, { entity_id: target, packages: [rule.package] });
				if (s.mode === rule.mode && s.mode !== 'limit') return;  // nothing changed
				if (s.mode === 'pause') {
					if (rule.mode === 'block') { await call('unblock_app', {}); await wait(1000); }
					return pause('pause_app');  // keeps the current rule, to be put back on resume
				}
				// leaving a pause: put the saved rule back first, so a later resume_app does not overwrite the new one
				if (rule.mode === 'pause') { await pause('resume_app'); await wait(1000); }
				if (s.mode === 'block') return call('block_app', {});
				// a blocked app must be unblocked before a limit can be set on it
				if (rule.mode === 'block') { await call('unblock_app', {}); await wait(1000); }
				return call('set_app_daily_limit', { minutes: s.mode === 'always' ? -2 : s.mode === 'none' ? -1 : s.minutes });
			},
		});
	}

	_bonusDialog() {
		const t = (k) => this._t(k), lock = this._d('lock');
		const used = this._n(this._d('daily_screen_time')), limit = this._n(this._d('daily_limit'));
		this._open({
			title: t('bonus'), icon: 'mdi:timer-plus-outline', name: this._config.title || (lock && lock.attributes.friendly_name) || '',
			sub: isNaN(used) ? '' : hm(used) + (limit > 0 ? ' / ' + hm(limit) : ''),
			state: { minutes: 15 },
			fields: [{ icon: 'mdi:timer-plus-outline', title: t('bonus_min'), sub: t('bonus_sub'), stepper: { key: 'minutes', min: 5, max: 240, step: 5, fmt: hm } }],
			save: (s) => this._call('familylink', 'add_time_bonus', { entity_id: this._map.device.lock, bonus_minutes: s.minutes }),
		});
	}

	_dayDialog(day) {
		const c = this._map.child, t = (k) => this._t(k);
		const ids = { limit: c[`daily_limit_${day}`], start: c[`bedtime_${day}_start`], end: c[`bedtime_${day}_end`], sstart: c[`schooltime_${day}_start`], send: c[`schooltime_${day}_end`] };
		const at = (k) => toMin((this._hass.states[ids[k]] || {}).state);
		const now = { limit: this._n(this._hass.states[ids.limit]), start: at('start'), end: at('end'), sstart: at('sstart'), send: at('send') };
		const fields = [{ icon: 'mdi:timer-sand', title: t('daily_limit'), sub: t('limit_day'), stepper: { key: 'limit', min: 0, max: 1440, step: 15, fmt: hm } }];
		if (!isNaN(now.start)) fields.push({ icon: 'mdi:clock-start', title: t('bed_from'), sub: t('steps'), stepper: { key: 'start', step: 15, wrap: 1440, fmt: clock } });
		if (!isNaN(now.end)) fields.push({ icon: 'mdi:clock-end', title: t('bed_to'), sub: t('steps'), stepper: { key: 'end', step: 15, wrap: 1440, fmt: clock } });
		// a weekday without school time has these entities unavailable: no field, school time is switched on in Family Link
		if (!isNaN(now.sstart)) fields.push({ icon: 'mdi:school', title: t('school_from'), sub: t('steps'), stepper: { key: 'sstart', step: 15, wrap: 1440, fmt: clock } });
		if (!isNaN(now.send)) fields.push({ icon: 'mdi:school-outline', title: t('school_to'), sub: t('steps'), stepper: { key: 'send', step: 15, wrap: 1440, fmt: clock } });
		this._open({
			title: t('day_settings'), icon: 'mdi:calendar-edit', name: t('days')[Number(day) - 1], sub: '',
			state: { ...now }, fields,
			save: async (s) => {
				// only what changed: each write is a request to Google, and strict mode takes it as the new reference
				const moved = (k) => !isNaN(now[k]) && s[k] !== now[k];  // NaN: no such entity that day
				if (moved('limit')) await this._call('number', 'set_value', { entity_id: ids.limit, value: s.limit });
				const hhmm = (m) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}:00`;
				// each bound rewrites its slot with the other bound as the integration knows it: when both move,
				// the end waits for the new start to be read back, or it would put the old start back
				const settled = async (k) => {
					for (let i = 0; i < 20; i++) {
						if (toMin((this._hass.states[ids[k]] || {}).state) === s[k]) return;
						await new Promise((r) => setTimeout(r, 500));
					}
					throw new Error(t('not_confirmed'));
				};
				for (const [a, b] of [['start', 'end'], ['sstart', 'send']]) {
					if (moved(a)) await this._call('time', 'set_value', { entity_id: ids[a], time: hhmm(s[a]) });
					if (moved(b)) {
						if (moved(a)) await settled(a);
						await this._call('time', 'set_value', { entity_id: ids[b], time: hhmm(s[b]) });
					}
				}
			},
		});
	}
}

FamilyLinkCard.css = `
	:host { display: block; container-type: inline-size; }
	ha-card { overflow: hidden; }
	button { font: inherit; color: inherit; border: 0; background: none; cursor: pointer; padding: 0; }
	.msg { padding: 16px; opacity: 0.7; } .msg.err { color: var(--error-color); opacity: 1; }
	.head { display: flex; align-items: center; gap: 10px; padding: 14px 16px 8px; }
	.head > ha-icon, .lockbtn ha-icon { --mdc-icon-size: 28px; }
	.lockbtn { position: relative; width: 40px; height: 40px; margin: -6px -2px -6px -6px; border-radius: 20px; display: inline-flex; align-items: center; justify-content: center;
		background: rgba(var(--rgb-primary-text-color, 255, 255, 255), 0.08); }
	.lockbtn[data-tip]:hover::after { right: auto; left: 0; }
	.ringbtn { position: relative; width: 28px; height: 28px; border-radius: 14px; display: inline-flex; align-items: center; justify-content: center; opacity: 0.6; }
	.ringbtn ha-icon { --mdc-icon-size: 18px; }
	.ringbtn[data-tip]:hover::after { right: auto; left: 0; }
	.gear { margin-right: -6px; } .gear[data-tip]:hover::after { left: auto; right: 0; }
	.title { font-weight: 700; font-size: 15px; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.head > * { flex-shrink: 0; } .head > .title { flex-shrink: 1; }
	.battery { display: inline-flex; align-items: center; font-size: 12px; font-weight: 600; color: var(--warning-color); }
	.battery ha-icon { --mdc-icon-size: 14px; }
	.used { margin-left: auto; font-weight: 700; font-size: 14px; white-space: nowrap; }
	.plus { color: var(--success-color); font-weight: 600; }
	.track { height: 6px; border-radius: 3px; background: var(--divider-color); grid-column: 1 / 3; }
	.track > div { height: 100%; border-radius: 3px; background: var(--primary-color); }
	.track.big { height: 8px; margin: 0 16px 6px; }
	.track.big > div { background: var(--accent-color); }
	.window { text-align: center; font-size: 12px; opacity: 0.7; padding-bottom: 8px; }
	.window .why { color: var(--error-color); font-weight: 600; }
	.bonus { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-top: 1px solid var(--divider-color); }
	.btxt { flex: 1; min-width: 0; font-size: 13px; font-weight: 600; }
	.btxt small { display: block; font-weight: 400; opacity: 0.6; font-size: 12px; }
	.round { position: relative; width: 36px; height: 36px; border-radius: 18px; display: inline-flex; align-items: center; justify-content: center;
		background: rgba(var(--rgb-primary-text-color, 255, 255, 255), 0.08); opacity: 0.75; }
	.round.big { width: 40px; height: 40px; border-radius: 20px; }
	.round[disabled] { opacity: 0.3; cursor: default; }
	.round ha-icon { --mdc-icon-size: 20px; }
	[data-tip]:hover::after { content: attr(data-tip); position: absolute; bottom: calc(100% + 8px); right: 0; z-index: 2; white-space: nowrap; pointer-events: none;
		padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 400; color: #fff; background: rgba(40, 40, 40, 0.92); }
	.round.big[data-tip]:hover::after { right: auto; left: 0; }
	.tiles { display: flex; border-top: 1px solid var(--divider-color); }
	.tile { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 12px 4px; font-size: 13px; font-weight: 600; }
	.tile + .tile { border-left: 1px solid var(--divider-color); }
	.tile ha-icon { --mdc-icon-size: 26px; opacity: 0.6; }
	.tile.on { background: rgba(255, 225, 150, 0.11); }
	.tile.on ha-icon { color: var(--accent-color); opacity: 1; }
	.label { display: flex; align-items: center; gap: 8px; padding: 14px 16px 6px; font-size: 11px; font-weight: 600; letter-spacing: 1.2px; text-transform: uppercase; opacity: 0.55;
		border-top: 1px solid var(--divider-color); }
	.label::before { content: ''; width: 3px; height: 12px; border-radius: 2px; background: var(--accent-color); }
	.tabs { display: flex; border-bottom: 1px solid var(--divider-color); }
	.tab { flex: 1 1 auto; display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 10px 4px; font-size: 13px; font-weight: 600; opacity: 0.6;
		border-bottom: 3px solid transparent; white-space: nowrap; overflow: hidden; }
	.tab ha-icon { --mdc-icon-size: 18px; }
	.tab.on { opacity: 1; border-bottom-color: var(--accent-color); }
	.tab.on ha-icon { color: var(--accent-color); }
	.list { padding: 6px 16px 12px; }
	.cols { columns: 2; column-gap: 12px; }
	.row { display: grid; grid-template-columns: 1fr auto; gap: 4px 10px; padding: 6px 0; cursor: pointer; break-inside: avoid; font-size: 14px; line-height: 1.45; }
	.name { display: flex; align-items: center; gap: 6px; min-width: 0; }
	.name span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.name ha-icon { --mdc-icon-size: 13px; opacity: 0.7; flex: none; }
	.right { opacity: 0.7; white-space: nowrap; }
	.cols .row { padding: 4px 0; font-size: 13px; }
	.empty { padding: 6px 0; font-size: 14px; opacity: 0.6; text-align: center; }
	.week { display: flex; padding: 0 8px 10px; }
	.day { flex: 1; display: flex; flex-direction: column; align-items: center; padding: 6px 0; border-radius: 8px; }
	.day.on { background: rgba(255, 225, 150, 0.11); }
	.day.on small { color: var(--accent-color); font-weight: 700; }
	.day small { font-size: 11px; opacity: 0.7; } .day b { font-size: 14px; } .day i { font-style: normal; font-size: 9px; opacity: 0.5; }
	.pills, .add { display: flex; gap: 8px; flex-wrap: wrap; }
	.pill { padding: 8px 12px; border-radius: 18px; font-size: 13px; font-weight: 600; background: rgba(var(--rgb-primary-text-color, 255, 255, 255), 0.08); }
	.pill.on { background: var(--accent-color); color: #1c1c1e; }
	.pill[disabled] { opacity: 0.5; cursor: default; }
	.hint { font-size: 12px; opacity: 0.55; margin: 6px 0 10px; }
	.add input { flex: 1; min-width: 120px; font: inherit; font-size: 14px; color: inherit; padding: 8px 12px; border-radius: 18px; outline: none;
		border: 1px solid var(--divider-color); background: rgba(var(--rgb-primary-text-color, 255, 255, 255), 0.04); }
	.add input:focus { border-color: var(--accent-color); }
	.err { margin-top: 8px; font-size: 13px; color: var(--error-color); }
	.sites { margin-top: 12px; } .sites small { display: block; font-size: 11px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; opacity: 0.55; margin-bottom: 4px; }
	.site { display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 14px; cursor: pointer; }
	.site em { font-style: normal; font-size: 12px; } .site em.allow { color: var(--success-color); } .site em.block { color: var(--error-color); }
	.sitehead { display: flex; align-items: center; justify-content: space-between; margin: 12px 0 4px; }
	.sitehead small { font-size: 11px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; opacity: 0.55; }
	.site span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.mini { position: relative; flex: none; width: 28px; height: 28px; border-radius: 14px; display: inline-flex; align-items: center; justify-content: center; opacity: 0.6; }
	.mini ha-icon { --mdc-icon-size: 16px; }
	.empty.left { text-align: left; padding: 2px 0; font-size: 13px; }
	/* narrow card (half width, phone, card picker preview): icons and counts only */
	/* five tabs with their words: tighter between 460 and 560px, icons and counts only below (the word stays as a tooltip) */
	@container (max-width: 560px) { .tab { font-size: 12px; gap: 3px; padding: 10px 0; } .tab ha-icon { --mdc-icon-size: 16px; } }
	.tabs.tight .tab .lbl { display: none; }
	@container (max-width: 420px) {
		.btxt small { display: none; }
		.bonus { gap: 6px; padding: 8px 10px; }
		.round { width: 32px; height: 32px; } .round.big { width: 34px; height: 34px; }
		.head { gap: 6px; padding: 12px 12px 8px; } .title { font-size: 14px; } .used { font-size: 13px; } .ringbtn { width: 24px; }
		.tile { font-size: 12px; } .day b { font-size: 13px; } .day i { font-size: 8px; }
		.cols { columns: 1; }
	}
`;

/** A dialog appended to <body>: always dark, its draft in this element until Save. */
class FamilyLinkDialog extends HTMLElement {
	open(spec) {
		this._s = spec;
		this._state = { ...spec.state };
		this._busy = false; this._error = '';
		this.attachShadow({ mode: 'open' });
		this._key = (e) => { if (e.key === 'Escape' && !this._busy) this._close(); };
		document.addEventListener('keydown', this._key);
		this._render();
	}

	_close() { document.removeEventListener('keydown', this._key); this.remove(); }
	// Also clean up if the entire parent popup is dismissed during editing.
	disconnectedCallback() { if (this._key) document.removeEventListener('keydown', this._key); }

	async _save() {
		this._busy = true; this._error = ''; this._render();
		try {
			await this._s.save(this._state);
			this._close();
		} catch (err) {
			this._busy = false;
			this._error = (err && err.message) || String(err);
			this._render();
		}
	}

	_step(st, dir) {
		const v = this._state[st.key] + dir * st.step;
		this._state[st.key] = st.wrap ? (v + st.wrap) % st.wrap : Math.min(st.max, Math.max(st.min, v));
	}

	_render() {
		const s = this._s, t = s.t;
		const stepper = (st) => `<div class="step"><button data-dir="-1" data-key="${st.key}">&minus;</button><span>${st.fmt(this._state[st.key])}</span><button data-dir="1" data-key="${st.key}">+</button></div>`;
		// a field is an option (key + value), a switch (toggle), a link (href), or a label between groups
		const field = (f, i) => (f.label ? `<div class="lbl">${esc(f.label)}</div>` : `
			<div class="opt${f.key && this._state[f.key] === (f.toggle ? true : f.value) ? ' on' : ''}${f.key || f.href ? ' pick' : ''}" data-i="${i}"${f.toggle ? ` role="switch" aria-checked="${!!this._state[f.key]}"` : ''}>
				<div class="chip"><ha-icon icon="${f.icon}"></ha-icon></div>
				<div class="txt"><div>${esc(f.title)}</div>${f.sub ? `<small>${esc(f.sub)}</small>` : ''}</div>${f.stepper ? stepper(f.stepper) : ''}
				${f.toggle ? `<span class="sw${this._state[f.key] ? ' on' : ''}"></span>` : ''}${f.href ? '<ha-icon class="chev" icon="mdi:chevron-right"></ha-icon>' : ''}
			</div>`);
		this.shadowRoot.innerHTML = `
			<style>${FamilyLinkDialog.css}</style>
			<div class="veil"></div>
			<div class="sheet" role="dialog" aria-modal="true" aria-label="${esc(s.title)}">
				<div class="bar"><ha-icon icon="${s.icon}"></ha-icon><span>${esc(s.title)}</span><button class="x" aria-label="${esc(t('close'))}"><ha-icon icon="${this._inlineInCard ? 'mdi:chevron-left' : 'mdi:close'}"></ha-icon></button></div>
				<div class="app"><div class="txt"><div class="big">${esc(s.name)}</div>${s.sub ? `<small>${esc(s.sub)}</small>` : ''}</div></div>
				${s.input ? `<input class="in" data-input="${s.input.key}" placeholder="${esc(s.input.placeholder)}" autocomplete="off" value="${esc(this._state[s.input.key])}" ${this._busy ? 'disabled' : ''}>` : ''}
				${s.fields.map(field).join('')}
				${this._error ? `<div class="err">${esc(this._error)}</div>` : ''}
				<button class="save" ${this._busy ? 'disabled' : ''}><ha-icon icon="${this._busy ? 'mdi:loading' : s.saveIcon || 'mdi:content-save-outline'}"></ha-icon>${this._busy ? t('saving') : s.saveLabel || t('save')}</button>
			</div>`;
		const root = this.shadowRoot;
		if (this._inlineInCard) {
			// Use the existing parent popup for sizing and scrolling, not another fixed overlay.
			const style = document.createElement('style');
			style.textContent = `
				:host { position: static !important; inset: auto !important; z-index: auto !important; display: block !important; width: 100%; }
				.veil { display: none !important; }
				.sheet { width: 100% !important; max-height: none !important; overflow: visible !important; border-radius: 0 !important; }
			`;
			root.appendChild(style);
		}
		root.querySelector('.veil').addEventListener('click', () => this._busy || this._close());
		root.querySelector('.x').addEventListener('click', () => this._busy || this._close());
		root.querySelector('.save').addEventListener('click', () => this._busy || this._save());
		const input = root.querySelector('[data-input]');
		if (input) {
			// typing must not re-render (it would lose the caret): only the draft is updated
			input.addEventListener('input', () => { this._state[input.dataset.input] = input.value; });
			input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !this._busy) this._save(); });
			if (!this._busy && !this._focused) { this._focused = true; setTimeout(() => input.focus(), 50); }
		}
		root.querySelectorAll('.pick').forEach((o) => o.addEventListener('click', () => {
			if (this._busy) return;
			const f = s.fields[o.dataset.i];
			if (f.href) {
				this._close();
				history.pushState(null, '', f.href);
				window.dispatchEvent(new CustomEvent('location-changed'));
				return;
			}
			this._state[f.key] = f.toggle ? !this._state[f.key] : f.value;
			this._render();
		}));
		root.querySelectorAll('[data-dir]').forEach((b) => b.addEventListener('click', (e) => {
			e.stopPropagation();
			if (this._busy) return;
			const f = s.fields.find((x) => x.stepper && x.stepper.key === b.dataset.key);
			this._step(f.stepper, Number(b.dataset.dir));
			if (f.key) this._state[f.key] = f.value;  // touching the stepper of an option selects it
			this._render();
		}));
	}
}

FamilyLinkDialog.css = `
	:host { position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center; font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
	.veil { position: absolute; inset: 0; background: rgba(0, 0, 0, 0.55); }
	/* dvh: the height really visible on a phone (100vh counts the browser bars); the sheet scrolls when it is taller */
	.sheet { position: relative; width: min(440px, calc(100vw - 24px)); max-height: calc(100vh - 24px); max-height: calc(100dvh - 24px - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px));
		overflow: auto; overscroll-behavior: contain; box-sizing: border-box; padding: 16px; border-radius: 28px; background: #1c1c1e; color: #ebebf0; container-type: inline-size; }
	.bar { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 14px; margin-bottom: 14px; }
	.bar span { flex: 1; }
	button { font: inherit; color: inherit; border: 0; cursor: pointer; }
	.x { width: 44px; height: 44px; border-radius: 22px; background: rgba(255, 255, 255, 0.08); display: inline-flex; align-items: center; justify-content: center; }
	.app { margin: 0 2px 14px; }
	.opt { display: flex; align-items: center; gap: 14px; padding: 12px 14px; margin-bottom: 8px; border-radius: 18px; background: rgba(255, 255, 255, 0.06);
		border: 2px solid transparent; min-height: 48px; }
	.opt.pick { cursor: pointer; }
	.opt.on { border-color: var(--accent-color, #ff9800); }
	.chip { flex: none; width: 48px; height: 48px; border-radius: 24px; display: flex; align-items: center; justify-content: center; background: rgba(255, 225, 150, 0.11); }
	.opt.on .chip { background: var(--accent-color, #ff9800); color: #1c1c1e; }
	.lbl { margin: 14px 4px 8px; font-size: 11px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; color: #a5a5ac; }
	.chev { flex: none; color: #a5a5ac; }
	.sw { flex: none; position: relative; width: 52px; height: 32px; border-radius: 16px; background: rgba(255, 255, 255, 0.18); transition: background 0.15s; }
	.sw::after { content: ''; position: absolute; top: 4px; left: 4px; width: 24px; height: 24px; border-radius: 12px; background: #ebebf0; transition: left 0.15s; }
	.sw.on { background: var(--accent-color, #ff9800); } .sw.on::after { left: 24px; }
	.txt { flex: 1; min-width: 0; font-size: 17px; font-weight: 700; line-height: 1.2; }
	.txt .big { font-size: 20px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	small { display: block; margin-top: 3px; font-size: 13px; font-weight: 400; color: #a5a5ac; }
	.step { flex: none; display: flex; align-items: center; height: 44px; border-radius: 22px; background: rgba(255, 255, 255, 0.1); }
	.step button { width: 44px; height: 44px; background: none; font-size: 20px; }
	.step span { min-width: 64px; text-align: center; font-weight: 700; font-size: 15px; }
	.err { margin: 4px 2px 10px; font-size: 13px; color: #ff6b6b; }
	/* a narrow sheet (a phone): the stepper takes its own row under the text, or the title is squeezed to a few letters per line */
	@container (max-width: 390px) {
		.opt { flex-wrap: wrap; row-gap: 8px; }
		.opt .step { flex: none; width: calc(100% - 62px); margin-left: 62px; justify-content: space-between; }
		.opt .step span { flex: 1; }
	}
	.in { width: 100%; box-sizing: border-box; height: 52px; margin-bottom: 8px; padding: 0 16px; border-radius: 18px; font: inherit; font-size: 16px;
		color: inherit; background: rgba(255, 255, 255, 0.06); border: 2px solid var(--accent-color, #ff9800); outline: none; }
	.save { width: 100%; height: 52px; margin-top: 6px; border-radius: 26px; background: rgba(255, 255, 255, 0.1); font-weight: 600; font-size: 16px;
		display: flex; align-items: center; justify-content: center; gap: 8px; }
	.save[disabled] { opacity: 0.6; cursor: default; }
	.save[disabled] ha-icon { animation: spin 1s linear infinite; }
	@keyframes spin { to { transform: rotate(360deg); } }
`;

/** Visual editor: the device (the child follows from it), a title, compact, the language. */
class FamilyLinkCardEditor extends HTMLElement {
	setConfig(config) { this._config = config; this._render(); }
	set hass(hass) { this._hass = hass; this._render(); }

	_render() {
		if (!this._hass || !this._config) return;
		const fr = (this._hass.language || '').startsWith('fr');
		if (!this._form) {
			this._form = document.createElement('ha-form');
			this._form.computeLabel = (s) => ({
				device: fr ? 'Téléphone ou tablette' : 'Phone or tablet', title: fr ? 'Titre' : 'Title',
				compact: fr ? 'Compact (en-tête et bonus seulement)' : 'Compact (header and bonus only)', language: fr ? 'Langue' : 'Language',
				bonus: fr ? 'Barre de bonus (+15 / +30 / +60 min)' : 'Bonus bar (+15 / +30 / +60 min)',
				zoom: 'Zoom', height: fr ? 'Hauteur de la carte (px)' : 'Map height (px)',
			}[s.name]);
			this._form.addEventListener('value-changed', (e) => {
				const config = { ...e.detail.value };
				if (config.device !== deviceOfEntity(this._hass, this._config.entity)) delete config.entity;  // the device now decides
				Object.keys(config).forEach((k) => (config[k] === '' || config[k] === undefined) && delete config[k]);
				this._config = config;
				this.dispatchEvent(new CustomEvent('config-changed', { detail: { config }, bubbles: true, composed: true }));
			});
			this.appendChild(this._form);
		}
		this._form.hass = this._hass;
		// the card shows the bonus bar unless bonus is false: the switch is on when the option is absent
		this._form.data = { ...(this._config.type === 'custom:familylink-location-card' ? {} : { bonus: true }), ...this._config, device: this._config.device || deviceOfEntity(this._hass, this._config.entity) };
		this._form.schema = [
			// only phones and tablets: they carry the bonus buttons, the child's own device has none
			{ name: 'device', required: true, selector: { device: { filter: { integration: 'familylink' }, entity: { domain: 'button' } } } },
			{ name: 'title', selector: { text: {} } },
			...(this._config.type === 'custom:familylink-location-card'
				? [{ name: 'zoom', selector: { number: { min: 8, max: 19, mode: 'slider' } } }, { name: 'height', selector: { number: { min: 150, max: 800, step: 10, mode: 'box' } } }]
				: [{ name: 'compact', selector: { boolean: {} } }, { name: 'bonus', selector: { boolean: {} } }]),
			{ name: 'language', selector: { select: { mode: 'dropdown', options: [{ value: 'en', label: 'English' }, { value: 'fr', label: 'Français' }, { value: 'pl', label: 'Polski' }] } } },
		];
	}
}

/**
 * custom:familylink-location-card: where the child is, on Home Assistant's own map card, under the usual header.
 *   device: <phone or tablet>   (or entity: device_tracker.<child>)   zoom: 15   height: 300   title, language
 * The refresh button asks the phone for a fresh fix (familylink.refresh_location): it uses the phone's battery.
 */
const LOC = {
	en: { title: 'Location', refresh: "Refresh the location (uses the phone's battery)", ago: '{t} ago', now: 'just now', off: 'Location tracking is off in the integration options' },
	fr: { title: 'Localisation', refresh: 'Actualiser la position (consomme la batterie du téléphone)', ago: 'il y a {t}', now: "à l'instant", off: "Le suivi de position est désactivé dans les options de l'intégration" },
};

LOC.pl = {
    title: 'Lokalizacja',
    refresh: 'Odśwież lokalizację (zużywa baterię telefonu)',
    ago: '{t} temu',
    now: 'przed chwilą',
    off: 'Śledzenie lokalizacji jest wyłączone w ustawieniach integracji',
};

class FamilyLinkLocationCard extends HTMLElement {
	setConfig(config) {
		if (!config || (!config.device && !config.entity)) throw new Error('familylink-location-card: choose the device (phone or tablet)');
		this._config = config;
		this._tracker = config.entity && config.entity.startsWith('device_tracker.') ? config.entity : null;
		this._looked = false;  // the tracker is looked up once per config
		if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
	}

	static getStubConfig(hass) { return { device: FamilyLinkCard.getStubConfig(hass).device }; }  // no bonus bar on this card
	static getConfigElement() { return document.createElement('familylink-card-editor'); }
	getCardSize() { return 6; }
	getGridOptions() { return { columns: 12, min_columns: 6, rows: 'auto' }; }

	_t(key) { const l = (this._config.language || this._hass.language || 'en').slice(0, 2); return (LOC[l] || LOC.en)[key]; }

	set hass(hass) {
		this._hass = hass;
		if (!this._tracker) return this._looked ? undefined : this._resolve();
		if (this._map) this._map.hass = hass;
		const st = hass.states[this._tracker];
		const seen = st ? st.last_updated : 'x';
		if (seen !== this._seen || !this.shadowRoot.querySelector('ha-card')) { this._seen = seen; this._render(); }
	}

	_resolve() {
		if (this._resolving) return;
		const entity = this._config.entity || entityOfDevice(this._hass, this._config.device);
		this._resolving = this._hass.callWS({ type: 'familylink/card_entities', entity_id: entity })
			.then((r) => { this._tracker = r.child && r.child.location; })
			.catch(() => setTimeout(() => { this._looked = false; }, 30000))  // Home Assistant restarting: ask again later
			.finally(() => {
				this._resolving = null;
				// no tracker (location off): say so once, not a websocket call per state change of the house
				this._looked = true;
				if (this._tracker) this.hass = this._hass;
				else this.shadowRoot.innerHTML = `<style>${FamilyLinkLocationCard.css}</style><ha-card><div class="msg">${this._t('off')}</div></ha-card>`;
			});
	}

	async _render() {
		const st = this._hass.states[this._tracker], t = (k) => this._t(k);
		const place = st ? (st.attributes.place_name || (this._hass.formatEntityState ? this._hass.formatEntityState(st) : st.state)) : '';
		const at = st && Date.parse(st.attributes.location_timestamp || st.last_updated);
		const min = at ? Math.max(0, Math.round((Date.now() - at) / 60000)) : NaN;
		const age = isNaN(min) ? '' : min < 1 ? t('now') : t('ago').replace('{t}', min < 60 ? `${min} min` : `${Math.round(min / 60)} h`);
		if (!this.shadowRoot.querySelector('ha-card')) {
			this.shadowRoot.innerHTML = `<style>${FamilyLinkLocationCard.css}</style><ha-card>
				<div class="head"><span class="title"></span><span class="place"><ha-icon icon="mdi:map-marker"></ha-icon><b></b></span><small class="age"></small>
					<button class="refresh" data-tip="${esc(t('refresh'))}" aria-label="${esc(t('refresh'))}"><ha-icon icon="mdi:refresh"></ha-icon></button></div>
				<div class="map" style="height:${Number(this._config.height) || 300}px"></div></ha-card>`;
			this.shadowRoot.querySelector('.refresh').addEventListener('click', (e) => this._refresh(e.currentTarget));
			// Home Assistant's own map card, so tiles, zones and dark mode behave as everywhere else
			const helpers = await window.loadCardHelpers();
			// the map card is loaded on demand: a first element triggers the load, the real one is made once it is defined
			if (!customElements.get('hui-map-card')) { helpers.createCardElement({ type: 'map', entities: [] }); await customElements.whenDefined('hui-map-card'); }
			this._map = await helpers.createCardElement({ type: 'map', entities: [{ entity: this._tracker }], default_zoom: Number(this._config.zoom) || 15, theme_mode: 'auto', aspect_ratio: '100%' });
			this._map.hass = this._hass;
			this.shadowRoot.querySelector('.map').appendChild(this._map);
			// the map card keeps its own aspect ratio (taller than our box, so the marker ends up out of view): make it fill the box, then fit again
			setTimeout(() => {
				const sr = this._map.shadowRoot;
				if (!sr) return;
				const css = document.createElement('style');
				css.textContent = 'ha-card, #root { height: 100% !important; padding-bottom: 0 !important; } ha-map { height: 100% !important; }';
				sr.appendChild(css);
				const m = sr.querySelector('ha-map');
				if (m && m.fitMap) setTimeout(() => m.fitMap(), 100);
			}, 500);
		}
		this.shadowRoot.querySelector('.title').textContent = this._config.title || t('title');
		this.shadowRoot.querySelector('.place b').textContent = place;
		this.shadowRoot.querySelector('.age').textContent = age;
	}

	async _refresh(btn) {
		if (btn.classList.contains('busy')) return;
		btn.classList.add('busy');
		try { await this._hass.callService('familylink', 'refresh_location', { entity_id: this._tracker }); } catch (err) { /* the integration logs it */ }
		setTimeout(() => btn.classList.remove('busy'), 4000);
	}
}

FamilyLinkLocationCard.css = `
	ha-card { overflow: hidden; }
	button { font: inherit; color: inherit; border: 0; background: none; cursor: pointer; padding: 0; }
	.msg { padding: 16px; opacity: 0.7; }
	.head { display: flex; align-items: center; gap: 8px; height: 40px; padding: 0 12px 0 16px; border-bottom: 1px solid var(--divider-color); }
	.title { font-size: 15px; font-weight: 700; }
	.place { display: inline-flex; align-items: center; gap: 3px; min-width: 0; font-size: 13px; color: var(--accent-color); }
	.place ha-icon { --mdc-icon-size: 14px; }
	.place b { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.age { margin-left: auto; font-size: 12px; color: var(--secondary-text-color); white-space: nowrap; }
	.refresh { position: relative; width: 32px; height: 32px; border-radius: 16px; display: inline-flex; align-items: center; justify-content: center; }
	.refresh ha-icon { --mdc-icon-size: 20px; }
	.refresh.busy ha-icon { animation: spin 1s linear infinite; }
	@keyframes spin { to { transform: rotate(360deg); } }
	[data-tip]:hover::after { content: attr(data-tip); position: absolute; top: calc(100% + 6px); right: 0; z-index: 2; white-space: nowrap; pointer-events: none;
		padding: 4px 8px; border-radius: 4px; font-size: 12px; color: #fff; background: rgba(40, 40, 40, 0.92); }
	/* the map card inside: no frame of its own, it fills the space under the header */
	.map { --ha-card-border-width: 0; --ha-card-border-radius: 0; --ha-card-box-shadow: none; }
	.map > * { display: block; height: 100%; }
`;

// Loaded by the integration on every page; a copy may also be a dashboard resource: define once.
if (!customElements.get('familylink-card')) {
	customElements.define('familylink-card-editor', FamilyLinkCardEditor);
	customElements.define('familylink-dialog', FamilyLinkDialog);
	customElements.define('familylink-card', FamilyLinkCard);
	customElements.define('familylink-location-card', FamilyLinkLocationCard);
	window.customCards = window.customCards || [];
	window.customCards.push({ type: 'familylink-card', name: 'Family Link', description: 'A Family Link device: screen time, bonus, apps and their rules, weekly limits.', preview: true });
	window.customCards.push({ type: 'familylink-location-card', name: 'Family Link location', description: "Where the child is, with a button to refresh the phone's position.", preview: true });
}

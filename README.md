# Gazzettino giornaliero Telegram

Automazione che, giornalmente (o su richiesta manuale), legge tutti i
messaggi scambiati in un gruppo Telegram organizzato a topic e genera un
riepilogo. Due formati disponibili:
- **`newspaper`** (default): una vera prima pagina di giornale, generata
  come immagine — titolo di apertura, occhiello e articolo per il tema più
  rilevante della giornata, più un articolo breve per ciascun topic attivo.
- **`text`**: messaggio testuale con punti salienti trasversali + dettaglio
  a elenco puntato per ciascun topic.

## Come funziona

- **Lettura messaggi**: [Telethon](https://docs.telethon.dev) (libreria
  MTProto, gratuita) con il tuo account Telegram personale. Non usa un bot,
  perché la Bot API non permette di leggere la cronologia di una chat: serve
  un account utente per poter recuperare retroattivamente i messaggi di un
  giorno qualsiasi, sia in automatico che a comando.
- **Testi**: OpenAI API (modello configurabile, default `gpt-4o-mini`).
- **Pagine**: template HTML/CSS in stile giornale, trasformato in immagini
  PNG con [Playwright](https://playwright.dev/python/) (Chromium headless).
  Il giornale si divide su due pagine quando ci sono almeno 4 articoli, con
  gli articoli ripartiti in modo da bilanciare il volume di testo; sotto
  quella soglia resta una pagina sola.
- **Invio**: per ora il report arriva in DM privato (Saved Messages, cioè
  messaggio a "te stesso"). In futuro, quando validato, si può spostare in un
  topic dedicato del gruppo cambiando solo configurazione (vedi sotto). Le
  pagine vengono inviate come foto (raggruppate in un album se sono più di
  una), così sono leggibili in anteprima senza scaricarle: per resistere
  alla ricompressione di Telegram vengono renderizzate a risoluzione doppia.
  Se Telegram rifiuta l'immagine perché troppo grande, l'invio ripiega
  automaticamente sul documento.
- **Scheduling**: GitHub Actions, con un cron giornaliero e un trigger
  manuale (`workflow_dispatch`) per i run on-demand — gira anche a PC spento.

## Setup

### 1. Credenziali app Telegram (gratuito)

Vai su https://my.telegram.org, fai login con il tuo numero, sezione
"API development tools", crea una app. Otterrai `api_id` e `api_hash`.

### 2. Genera la sessione Telethon (in locale, una tantum)

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# compila TELEGRAM_API_ID e TELEGRAM_API_HASH in .env
python generate_session.py
```

Ti verrà chiesto il numero di telefono e il codice ricevuto via Telegram (ed
eventualmente la password 2FA, se attiva). Lo script stampa:
- la `TELEGRAM_SESSION` da salvare come secret (**non condividerla e non
  committarla**: equivale ad avere accesso al tuo account Telegram);
- l'elenco dei tuoi gruppi/canali con il relativo ID, da usare come
  `TELEGRAM_GROUP_ID` (il gruppo con i topic che vuoi riepilogare).

### 3. Chiave OpenAI

Crea una API key su https://platform.openai.com/api-keys.

### 4. Configura i secrets su GitHub

Nel repo GitHub (dopo aver fatto push di questo progetto), vai in
**Settings → Secrets and variables → Actions** e crea questi secrets:

| Nome | Valore |
|---|---|
| `TELEGRAM_API_ID` | da my.telegram.org |
| `TELEGRAM_API_HASH` | da my.telegram.org |
| `TELEGRAM_SESSION` | stampata da `generate_session.py` |
| `TELEGRAM_GROUP_ID` | ID del gruppo, da `generate_session.py` |
| `OPENAI_API_KEY` | da platform.openai.com |

Opzionali, in **Variables** (non secrets, valori non sensibili) se vuoi
personalizzare i default:
- `REPORT_DESTINATION` (default `me`)
- `REPORT_TOPIC_ID` (per la fase futura, invio in un topic del gruppo)
- `REPORT_TIMEZONE` (default `Europe/Rome`)
- `NEWSPAPER_NAME` (nome della testata in prima pagina; default: nome del
  gruppo Telegram, recuperato automaticamente)

### 5. Primo test manuale

Prima di affidarti allo schedule automatico, lancia il workflow a mano da
GitHub: tab **Actions → Gazzettino giornaliero Telegram → Run workflow**
(puoi scegliere il formato `newspaper`/`text` e opzionalmente indicare una
data `YYYY-MM-DD` passata da riepilogare). Verifica che il DM con il
gazzettino arrivi correttamente.

Puoi anche testare in locale:

```bash
python main.py --date 2026-07-27                  # prima pagina (default)
python main.py --date 2026-07-27 --format text     # formato testuale
```

## Passare all'invio nel topic del gruppo

Quando il formato ti convince e vuoi che il gazzettino sia visibile a tutto
il gruppo:
1. Crea (o individua) il topic dedicato nel gruppo e prendine l'ID.
2. Imposta `REPORT_DESTINATION` = ID del gruppo (uguale a
   `TELEGRAM_GROUP_ID`) e `REPORT_TOPIC_ID` = ID del topic.

Nessuna modifica al codice è necessaria.

## Note

- L'orario del cron in `.github/workflows/daily-report.yml` è in UTC:
  adattalo alle tue esigenze.
- Senza `--date`, il report riepiloga **il giorno precedente** (nel fuso
  orario `REPORT_TIMEZONE`): è pensato per il lancio notturno, ad esempio
  alle 3:00, così copre la giornata appena conclusa.
- Il "giorno" da riepilogare è calcolato nel fuso orario `REPORT_TIMEZONE`
  (default Europe/Rome).
- Per gruppi molto attivi, i riassunti passano automaticamente a una
  modalità map-reduce (riassunti parziali poi unificati) per restare dentro
  ai limiti di contesto del modello OpenAI scelto.

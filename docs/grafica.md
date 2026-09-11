# Grafica del gazzettino

Questo documento risponde a una domanda sola: **come si aggiunge grafica
alle notizie senza che diventi pacchiana.** La risposta breve sta nella
prossima riga; il resto sono le conseguenze.

> Un elemento grafico si tiene in pagina solo se dice qualcosa che il
> testo non dice.

Tutto quello che non passa questo filtro è decorazione, e la decorazione è
esattamente ciò che fa sembrare improvvisata una testata. Le due sole
eccezioni ammesse sono il capolettera e il quadratino di fine pezzo:
non aggiungono un linguaggio nuovo, sono convenzioni tipografiche vecchie
di secoli che dicono dove comincia e dove finisce un articolo.

## Le cinque regole operative

Sono la traduzione pratica del principio, e vanno lette come vincoli, non
come consigli.

1. **Una sola famiglia di forme.** Niente angoli arrotondati, niente
   ombre portate, niente gradienti. La struttura la fanno i regoli e gli
   allineamenti. Ogni scorciatoia su questo punto si somma alle altre.
2. **Una sola famiglia di colori.** Navy `#0c2340` e azzurro `#17a3e0`
   con le loro gradazioni. Un grafico con cinque colori diversi non è più
   informativo di uno con cinque gradazioni: è solo più rumoroso.
3. **Un solo carattere tipografico.** Archivo, tre pesi. Il secondo
   caratttere in pagina è il segnale più affidabile che qualcosa è stato
   aggiunto senza pensarci.
4. **Mai le emoji nel layout.** Hanno colore, volume e stile propri, e non
   sono le tue: sono la via più rapida al pacchiano. Se serve un segno,
   si disegna (vedi i pittogrammi).
5. **Meglio niente che mediocre.** Se la fonte non regge — un topic senza
   un'icona sensata, una giornata senza dati per il grafico — l'elemento
   non va in pagina. È la regola che alla fine ha portato a togliere del
   tutto le immagini: vedi sotto.

## Cosa c'è in pagina

Gli elementi si accendono uno per uno da `GraphicsOptions`
(`report/newspaper.py`), perché non hanno lo stesso rischio. Per vederli
tutti renderizzati alla dimensione reale:

```bash
python catalogo.py          # scrive catalogo.png
```

### Attivi di default

| Elemento | Cosa dice | Dove sta |
|---|---|---|
| **Dato grande** | quanto ha dominato il topic principale | sotto l'indice |
| **Capolettera** | dove comincia il pezzo principale | primo paragrafo dell'apertura |
| **Quadratino di fine pezzo** | dove finisce un articolo | ultima riga di ogni pezzo |
| **Barretta di peso** | quanto pesa quel topic rispetto al più discusso | riga del contatore messaggi |
| **Pittogrammi dei topic** | distingue i topic a colpo d'occhio | tag dei pezzi e indice |
| **Barra delle proporzioni** | quanto ha pesato ogni topic sulla giornata | sotto l'indice |
| **Box «In breve»** | i topic minori, senza fingere che siano notizie | ultima pagina |
| **Andamento orario** | *quando* è successo: la forma della giornata | fascia navy di chiusura |

### Le immagini: nessuna

Il gazzettino non ha immagini. L'unica cosa raster in pagina è il logo
della testata.

Ci sono voluti tre tentativi per arrivarci, e vale la pena dire come è
andata perché la conclusione non è ovvia. Prima una foto grande sotto
l'apertura, poi anche nei pezzi, poi solo un provino piccolo in fondo:
ogni giro sembrava il problema fosse *come* l'immagine veniva messa in
pagina — ritaglio, proporzioni, trattamento cromatico, cornice.

Non era quello. Su una giornata reale del gruppo le immagini scelte erano
un fermo immagine di un video con i sottotitoli impressi, lo screenshot
di un articolo di giornale e uno scarabocchio con un logo sopra. Non sono
fotografie editoriali: sono **artefatti di conversazione**, che
funzionano a dimensione chat e dentro il contesto dei messaggi che li
spiegano. Fuori di lì non dicono niente, a nessuna scala — e un elemento
che non dice niente non sta in pagina, che è la regola con cui questo
documento comincia.

Il codice per gestirle (proporzioni dal messaggio, cornice invece del
taglio, colonnino per le miniature dei video, bicromia, provenienza delle
anteprime dei link) è in `git log`, se un giorno il gruppo pubblicasse
foto vere.

**Quindi cosa riempie la pagina?** La tipografia e i dati: il dato
grande, i tre gradini di ogni articolo, il box «In breve», il capolettera,
il grafico orario, la barra delle proporzioni. Una pagina fatta di questi
non ha buchi da tappare.

### Titolo, sommario, testo

Un articolo ha tre gradini: **titolo, sommario, testo**. Senza il gradino
di mezzo la pagina è un elenco di blocchi, non un giornale — ed è quello
che si vedeva sull'edizione vera, dove parecchi pezzi uscivano come un
unico paragrafo in grassetto senza corpo.

La causa non era il layout ma il formato chiesto al modello. Era
posizionale — «RIGA 1: il titolo, dalla RIGA 2 il corpo» — e falliva nel
modo peggiore: quando il modello rispondeva in un blocco unico, il parser
prendeva **tutto il testo come titolo** e l'articolo usciva senza corpo,
con un paragrafo intero stampato a 40px.

Ora il formato è a etichette (`TITOLO:` / `SOMMARIO:` / `TESTO:`), che
sono molto più difficili da sbagliare, e il parser le riconosce anche
fuori ordine, senza due punti e su più righe. Ma la difesa vera è
l'invariante finale (`_enforce_lengths` in `report/summarize.py`):
**qualunque cosa risponda il modello, quello che esce sono un titolo
corto e un sommario di una frase**. L'eccedenza scala sempre verso il
basso — dal titolo al sommario, dal sommario al corpo — perché è l'unica
direzione che non perde testo. Serve a entrambi i livelli: appena tappato
il titolo, il difetto si è ripresentato un gradino più giù, con il
sommario che si prendeva tutto l'articolo e sotto restava «Nessun
dettaglio disponibile». Un h3 con dentro un paragrafo
non è un difetto di stile: è una pagina rotta, e il layout non può essere
l'unico posto in cui ce ne accorgiamo.

### Gli orari sono nel fuso del report, non in UTC

Il grafico del ritmo della giornata è stato per un po' **ruotato di due
ore**, e la cosa peggiore è che sembrava plausibile lo stesso: le
colonne c'erano, la forma era credibile, semplicemente il picco non
cadeva dove era successo il fatto.

La causa: Telethon consegna `message.date` in UTC, e `SimpleMessage` se lo
teneva così. I confini del giorno erano giusti (il confronto fra datetime
consapevoli funziona), ma **ogni ora mostrata** era quella di Greenwich:
il grafico, l'ora di punta nelle statistiche, l'orario della frase del
giorno, e gli orari nel transcript dato al modello — che quindi scriveva
i pezzi leggendo orari sfalsati.

Non era un semplice scostamento ma una rotazione: nella finestra
[00:00, 24:00) ora italiana, un messaggio dell'una di notte finiva nella
colonna delle 23. Su una partita delle 18:30 il picco si leggeva alle
16:00.

La conversione si fa **una volta sola in `fetch.py`**, dove il fuso è
noto: `SimpleMessage.timestamp` è per contratto nel fuso configurato.
Farla a valle avrebbe significato passare il fuso a chiunque legga
un'ora, e bastava dimenticarne uno per riavere il difetto.

### L'impaginazione bilancia le pagine

Il riempimento avido decide bene *quante* pagine servono e male *come*
riempirle: caricando ogni pagina fino al tetto, l'ultima si prende gli
avanzi. Misurate su tre pagine: 1875, 999 e 2084 px — una piena, una
vuota, una piena. Dopo il ribilanciamento verso un'altezza obiettivo:
1875, 1314, 1769. Il numero di pagine non cambia mai, e se la
redistribuzione sfondasse il tetto si tiene il risultato avido.

Nella stessa occasione è caduta un'assunzione diventata falsa: «sotto le
quattro notizie basta una pagina sola». Valeva quando la chiusura pesava
340px; ora che porta anche il box «In breve» ne pesa molto di più, e tre
trafiletti bastavano a mandare la pagina unica oltre il tetto. La soglia ora è una condizione sulla *altezza*, non solo sul
numero.

### Il dato grande e il box «In breve»

Due elementi nati dallo stesso problema: **tredici topic attivi
producevano tredici articoli della stessa forma**, cioè quattro pagine
senza gerarchia — una schedina, non un giornale.

- **Il dato grande** (`number_block`) sta sotto l'indice: il numero di
  messaggi del topic più discusso, alla scala a cui i numeri si guardano
  invece di leggerli, più la sua quota sulla giornata. Dà peso visivo
  alla testa della pagina riempiendo lo spazio di informazione, che è
  l'unico modo onesto di riempirlo.
- **Il box «In breve»** (`brief_box`) raccoglie i topic oltre il quinto
  (`MAX_FULL_ARTICLES`) in due colonne di soli titoli. Un trafiletto di
  quattro righe per un topic da sei messaggi è una promessa che il
  contenuto non mantiene; una riga di titolo la mantiene. La gerarchia si
  vede solo se qualcosa è grande e qualcos'altro è piccolo.

## Cosa è stato scartato (e perché)

### Illustrazioni generate dall'IA

È l'idea che viene per prima quando si dice "aggiungiamo grafica". È
stata implementata per intero, provata, e poi rimossa: il codice sta
nella storia di git (`git log --diff-filter=D -- report/illustration.py`)
per chi volesse ripartire da lì, ma la prova ha confermato l'obiezione di
principio invece di smentirla.

**Cosa è successo.** L'implementazione era incorniciata bene: uno stile
unico bloccato in una costante e indipendente dalla notizia, il soggetto
ricavato da un passaggio di testo separato che escludeva volti, maglie,
stemmi e scritte, l'immagine passata dallo stesso filtro duotone delle
foto vere, la didascalia sempre esplicita. Su un titolo di mercato —
prestito, firma attesa entro giovedì, slot in lista da liberare — è
uscita una linoleografia pulita e ben fatta: un pallone appoggiato su un
contratto, con una penna accanto.

**Perché non basta.** Quell'immagine illustra *la categoria, non la
notizia*. Andrebbe identica su qualunque titolo di mercato, oggi e fra
due anni; del titolo specifico non raccoglie niente. Ed è un esito
strutturale, non un sorteggio sfortunato: sono proprio i vincoli
necessari — niente persone, niente scritte, niente stemmi, che senza si
finisce con volti di giocatori veri e testo sbagliato in prima pagina — a
lasciare disponibili solo oggetti di scena generici. Stringere il prompt
per renderla più specifica porta a immagini più strane, non più
pertinenti.

Torna quindi il principio: **un'illustrazione generata non dice niente
che il testo non dica già**. Con una foto vera del gruppo il problema non
si pone — quella *è* la giornata, non una rappresentazione della
giornata.

**E il caso senza foto?** Non è un buco da riempire. La prima pagina
senza immagine regge da sola — titolo, occhiello e capolettera fanno il
lavoro — e ci guadagna: i 420px liberati fanno salire un secondo pezzo
sopra il taglio. Confrontabile con `python preview.py --no-hero`.

Se un giorno la si volesse riprendere, le tre difese dell'impianto
rimosso restano quelle giuste (stile bloccato, soggetto da un passaggio
separato, stesso trattamento cromatico delle foto vere). Quello che
manca, e che nessuna di quelle difese risolve, è un modo di legare
l'immagine al fatto e non all'argomento.

### Classifica dei partecipanti

Tecnicamente gratis: i dati ci sono già. Scartata per motivi non tecnici —
una classifica di chi scrive di più in un gruppo di amici cambia il modo
in cui le persone ci scrivono dentro, e non in meglio. Il numero
aggregato di partecipanti dice quel che serve.

## Lavorare sulla grafica

Il layout è la parte che si itera di più ed è l'unica che non ha bisogno
di dati veri per essere giudicata. Due script girano offline, senza
toccare né Telegram né OpenAI:

```bash
python preview.py                          # pagine con dati finti
python preview.py --plain                  # com'era prima di questo modulo
python preview.py --no-glyphs              # spegne un singolo elemento
python catalogo.py                         # campionario di tutti gli elementi
```

Serve Chromium. Se l'ambiente ne ha già uno con una revisione
diversa da quella che Playwright si aspetta, si indica con
`CHROMIUM_EXECUTABLE_PATH=/percorso/al/chrome`.

Un promemoria sulle dimensioni: le pagine vengono renderizzate a 1080px
CSS e inviate come foto su Telegram, che le ricomprime in JPEG. Ogni
elemento grafico va giudicato **dopo** quella compressione, non nel PNG
sorgente — è il motivo per cui i tratti sono spessi, i contrasti alti e
non c'è niente sotto i 15px.

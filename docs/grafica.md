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
5. **Meglio niente che mediocre.** Se la fonte non regge — foto sotto i
   600px, topic senza un'icona sensata, giornata senza dati per il
   grafico — l'elemento non va in pagina. Una pagina tipografica pulita è
   sempre una pagina valida; una pagina con dentro un'immagine sgranata
   non lo è.

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
| **Provino «Il giorno in immagini»** | cosa ha pubblicato il gruppo | ultima pagina |
| **Andamento orario** | *quando* è successo: la forma della giornata | fascia navy di chiusura |
| **Bicromia** | niente, ma *uniforma*: lega le immagini alla testata | provino, e immagini in linea se accese |

Il **trattamento cromatico** uniforma immagini che arrivano da telefoni e
sorgenti diverse. Tre opzioni (`photo_treatment`):

- `mono` — bianco e nero. Uniforma ma spegne. Era il comportamento
  precedente.
- `duotone-soft` — **default**. Ombre navy, mezzitoni grigio-blu. La foto
  resta una fotografia; l'appartenenza alla testata la danno le ombre.
- `duotone` — mezzitoni sull'azzurro del marchio. Si riconosce anche in
  miniatura nello scroll della chat, ma è una scelta forte: su un
  ritratto si vede parecchio.

### Le immagini: perché stanno solo nel provino

Questa è la sezione che ha cambiato idea più volte, e vale la pena
dire come è andata, perché la conclusione non è ovvia.

Il primo tentativo metteva una foto grande sotto l'apertura e nei pezzi.
Sulla pagina vera il risultato era brutto, e non per un difetto di
impaginazione: dipende da **cosa sono davvero le immagini di una chat**.
Su una giornata reale del gruppo, le tre immagini scelte erano un fermo
immagine di un video con i sottotitoli impressi, lo screenshot di un
articolo di giornale e uno scarabocchio con un logo sopra.

Non sono fotografie editoriali. Sono **artefatti di conversazione**:
funzionano a dimensione chat, dentro il loro contesto, in mezzo ai
messaggi che li spiegano. Ingranditi a piena pagina non aggiungono
informazione — la tolgono, perché occupano lo spazio di qualcosa che
potrebbe darla. Nessun trattamento cromatico, nessuna regola di ritaglio
e nessuna cornice risolve questo: il problema non è come l'immagine è
messa in pagina, è che a quella scala non dice niente.

Quindi, di default (`inline_photos = False`):

- **niente immagini nell'apertura e negli articoli**. Lo spazio va al
  titolo, all'occhiello e al testo, che a quella scala l'informazione ce
  l'hanno;
- le immagini restano nel **provino** «Il giorno in immagini» in fondo,
  fino a otto, piccole. È la scala giusta: uno screenshot lì si legge per
  quello che è — «il gruppo ha pubblicato questo» — senza pretendere di
  illustrare una notizia. Ogni riquadro porta l'etichetta del suo topic.

Le immagini grandi si riaccendono con `inline_photos = True`
(`python preview.py --foto-in-pagina`): il codice per gestirle c'è tutto
— proporzioni dal messaggio, cornice invece del taglio per le verticali,
colonnino per le miniature dei video — e torna utile il giorno in cui il
gruppo pubblicasse foto vere.

**Se le immagini non riempiono la pagina, cosa la riempie?** La
tipografia e i dati. Sono gli elementi qui sotto: il dato grande, il box
«In breve», il capolettera, il grafico orario, la barra delle
proporzioni. Una pagina fatta di questi non ha buchi da tappare.

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
l'invariante finale (`_enforce_headline` in `report/summarize.py`):
**qualunque cosa risponda il modello, quello che esce è un titolo corto**.
Oltre 90 caratteri il testo viene tagliato alla prima fine di frase, il
resto scala nel sommario e poi nel corpo. Un h3 con dentro un paragrafo
non è un difetto di stile: è una pagina rotta, e il layout non può essere
l'unico posto in cui ce ne accorgiamo.

### L'impaginazione bilancia le pagine

Il riempimento avido decide bene *quante* pagine servono e male *come*
riempirle: caricando ogni pagina fino al tetto, l'ultima si prende gli
avanzi. Misurate su tre pagine: 1875, 999 e 2084 px — una piena, una
vuota, una piena. Dopo il ribilanciamento verso un'altezza obiettivo:
1875, 1314, 1769. Il numero di pagine non cambia mai, e se la
redistribuzione sfondasse il tetto si tiene il risultato avido.

Nella stessa occasione è caduta un'assunzione diventata falsa: «sotto le
quattro notizie basta una pagina sola». Valeva quando la chiusura pesava
340px; ora che porta anche il box «In breve» e il provino ne pesa quasi
mille, e tre trafiletti bastavano a mandare la pagina unica ben oltre il
tetto. La soglia ora è una condizione sulla *altezza*, non solo sul
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

### Da dove arrivano le immagini

La catena è, in ordine: una foto scattata e pubblicata nel gruppo,
l'immagine dell'anteprima di un link condiviso nel gruppo, la copertina
del video YouTube del giorno, niente.

Il secondo anello è la risposta alla domanda «e se cercassimo l'immagine
online?». Cercarla davvero — un motore di ricerca immagini, o uno scraper
— porta tre problemi in una volta: quasi tutto quello che si trova è
protetto da diritti d'autore (foto d'agenzia, del club, dei quotidiani);
una ricerca per parole chiave restituisce facilmente il giocatore
sbagliato, una foto di tre anni fa o un fotomontaggio, e in un riepilogo
di cose vere un'immagine sbagliata è peggio di nessuna immagine; e
servirebbe un'API in più con la sua chiave e il suo costo.

L'anteprima di un link condiviso nel gruppo evita tutti e tre: è la
testata stessa ad aver scelto quell'immagine **per quel fatto preciso**,
Telegram l'ha già scaricata (quindi non serve nessuna richiesta
esterna: la prende lo stesso client Telethon), e soprattutto è materiale
che il gruppo ha messo lì — vale la stessa regola delle foto, non è la
macchina che pesca un'immagine a caso da internet.

Resta una cosa da sapere: quell'immagine non è del gruppo, è di chi ha
pubblicato l'articolo. Per questo la didascalia lo dice sempre — «Da Il
Mattino · link condiviso nel topic Mercato, 21:14» — e per questo una
foto vera del gruppo vince sempre sull'anteprima, anche con meno
reazioni. Se il gazzettino dovesse uscire dal gruppo che ha già visto
quelle anteprime, la questione dei diritti andrebbe guardata sul serio.

L'**andamento orario** è l'elemento che aggiunge di più, perché è l'unico
che porta in pagina un'informazione che il testo non ha: il gazzettino
racconta cosa si è detto, il grafico racconta che se n'è parlato tutto
d'un fiato dopo cena. Sta nella stessa fascia navy dei quattro numeri e li
completa invece di ripeterli.

- **Pittogrammi dei topic** (`topic_glyphs`) — set disegnato a mano, nove
  segni sulla stessa griglia e sullo stesso tratto: è l'omogeneità a
  salvarlo, non il singolo disegno. L'abbinamento topic → segno lo fa un
  elenco di parole chiave in `report/graphics.py`, **mai il modello**: un
  topic che cambia icona da un giorno all'altro è il modo migliore per
  non sembrare una testata. Un topic che non c'entra con nessuna icona
  ricade sui tre puntini.
- **Barra delle proporzioni** (`share_bar`) — quanto ha pesato ogni topic
  sulla giornata, sotto l'indice.
- **Fascia «Il giorno in immagini»** — vedi sopra.

Gli ultimi due elementi erano spenti all'inizio per prudenza, e sono
stati accesi perché sulla pagina vera la prudenza risultava in una pagina
povera: con tredici topic attivi e un'immagine sola l'edizione era una
colonna di testo. Si spengono uno per uno da `GraphicsOptions`, o
dall'anteprima con `--no-glyphs` e `--no-share`.

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
python preview.py --foto duotone           # bicromia piena invece che morbida
python preview.py --glyphs --share         # con gli elementi opzionali accesi
python preview.py --no-hero                # giornata senza foto
python catalogo.py                         # campionario di tutti gli elementi
```

Servono le dipendenze di sviluppo (`pip install -r requirements-dev.txt`):
oltre a quelle di produzione c'è Pillow, usato solo per generare la foto
di prova con cui si giudica il trattamento cromatico. Senza, l'anteprima
gira lo stesso e mostra la variante senza foto.

Serve anche Chromium. Se l'ambiente ne ha già uno con una revisione
diversa da quella che Playwright si aspetta, si indica con
`CHROMIUM_EXECUTABLE_PATH=/percorso/al/chrome`.

Un promemoria sulle dimensioni: le pagine vengono renderizzate a 1080px
CSS e inviate come foto su Telegram, che le ricomprime in JPEG. Ogni
elemento grafico va giudicato **dopo** quella compressione, non nel PNG
sorgente — è il motivo per cui i tratti sono spessi, i contrasti alti e
non c'è niente sotto i 15px.

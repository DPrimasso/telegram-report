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
| **Bicromia sulle foto** | niente, ma *uniforma*: rende usabile una foto qualsiasi da chat | foto di apertura |
| **Capolettera** | dove comincia il pezzo principale | primo paragrafo dell'apertura |
| **Quadratino di fine pezzo** | dove finisce un articolo | ultima riga di ogni pezzo |
| **Barretta di peso** | quanto pesa quel topic rispetto al più discusso | riga del contatore messaggi |
| **Andamento orario** | *quando* è successo: la forma della giornata | fascia navy di chiusura |

Il **trattamento delle fotografie** è la scelta che conta di più, perché è
quella che permette di mettere in pagina una foto qualsiasi senza che la
pagina si sfaldi. Tre opzioni (`photo_treatment`):

- `mono` — bianco e nero. Uniforma ma spegne. Era il comportamento
  precedente.
- `duotone-soft` — **default**. Ombre navy, mezzitoni grigio-blu. La foto
  resta una fotografia; l'appartenenza alla testata la danno le ombre.
- `duotone` — mezzitoni sull'azzurro del marchio. Si riconosce anche in
  miniatura nello scroll della chat, ma è una scelta forte: su un
  ritratto si vede parecchio.

### Quante immagini, e come sono ritagliate

**Quante.** L'apertura più al massimo due pezzi secondari, uno per topic
(`MAX_ARTICLE_PHOTOS` in `report/photo.py`). Il limite non è tecnico: una
foto in pagina dice «questo pezzo conta più degli altri», e darne una a
tutti toglie il segnale invece di aggiungerlo. Quando la prima pagina non
ci sta, si toglie la foto e si tiene il testo — fra le due, la parte
rinunciabile è la foto.

**Come sono ritagliate.** Il riquadro prende le proporzioni
dell'immagine, non viceversa. Un riquadro ad altezza fissa andava bene
finché le immagini erano foto orizzontali; su un fermo immagine di un
video o su uno screenshot di telefono — che è la maggior parte di quello
che gira in una chat — ne buttava via i due terzi, tagliando esattamente
la parte con il soggetto.

Le dimensioni arrivano gratis dal messaggio: Telegram allega a ogni foto
l'elenco delle sue "size", quindi non serve aprire il file scaricato né
una libreria di immagini.

Restano un tetto e un pavimento (`HERO_MAX_HEIGHT`, `HERO_MIN_HEIGHT`),
perché la pagina ha una sua economia: una foto verticale a piena
larghezza sarebbe alta più di mille pixel e spingerebbe l'articolo fuori
dalla prima schermata. Sopra il tetto si ritaglia comunque, ma **dal
basso**, non dal centro: in una foto il soggetto sta quasi sempre nella
metà alta, e in un fermo immagine con i sottotitoli impressi quello che
si perde sono i sottotitoli.

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

### Spenti di default

- **Pittogrammi dei topic** (`topic_glyphs`) — set disegnato a mano, nove
  segni sulla stessa griglia e sullo stesso tratto: è l'omogeneità a
  salvarlo, non il singolo disegno. L'abbinamento topic → segno lo fa un
  elenco di parole chiave in `report/graphics.py`, **mai il modello**: un
  topic che cambia icona da un giorno all'altro è il modo migliore per
  non sembrare una testata. Restano spenti perché con i tag già colorati
  aggiungono un secondo segnale nello stesso punto, e perché un topic che
  non c'entra con nessuna icona ricade sui tre puntini, cioè su niente.
- **Barra delle proporzioni** (`share_bar`) — corretta e leggibile, ma
  l'indice a chip dice già i numeri. Nelle giornate con un topic
  dominante aggiunge poco; in quelle equilibrate diventa una fila di
  segmenti tutti uguali.

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

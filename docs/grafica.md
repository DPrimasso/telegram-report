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

È l'idea che viene per prima quando si dice "aggiungiamo grafica", ed è
anche quella con il rapporto rischio/resa peggiore. Il problema non è la
qualità delle immagini, che oggi è alta: è che **un'illustrazione generata
non dice niente che il testo non dica già**, e viola quindi il principio
alla radice. In più:

- lo stile cambia da un giorno all'altro anche a parità di prompt, e una
  testata che cambia registro grafico ogni giorno non sembra una testata;
- il modello mette scritte dentro le immagini, e le scritte sbagliate
  dentro un'immagine sono la cosa più vistosa che possa capitare in prima
  pagina;
- volti e simboli riconoscibili (maglie, stemmi, giocatori reali) sono
  proprio il caso in cui l'immagine generata si nota di più, ed è anche
  quello con i problemi di diritti;
- ha un costo per immagine e una latenza, dentro un job notturno che oggi
  non ha nessuna delle due.

Se in futuro la si vuole comunque, va incorniciata così: **un solo stile
bloccato in una costante** (per esempio linoleografia monocroma, nessun
testo, nessun volto), **passata dallo stesso filtro duotone** delle foto
vere così da non introdurre una seconda tavolozza, **con didascalia
esplicita** ("illustrazione generata"), e **solo come ricaduta** quando
non c'è né una foto del gruppo né una copertina YouTube — cioè nel caso
in cui oggi l'apertura resta tipografica, che comunque funziona.

### Foto sui pezzi secondari

Tentazione ovvia, visto che la seconda pagina è cinque blocchi di testo
uguali. Scartata perché le foto buone in un gruppo Telegram sono poche:
una per l'apertura si trova quasi sempre, cinque no. Il risultato reale
sarebbe stato un pezzo con la foto e quattro senza, cioè una gerarchia
falsa — sembrerebbe che quel pezzo conti di più, quando invece era solo
l'unico con un'immagine sopra i 600px. La barretta di peso risolve lo
stesso problema (spezzare la monotonia, dare una gerarchia) con
un'informazione vera.

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

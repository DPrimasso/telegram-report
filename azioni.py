"""Le 96 azioni della biblioteca: sedici per ciascuno dei sei toni.

Il primo tentativo aveva una sola descrizione per tono, e le sedici
immagini del battibecco avevano tutte lo stesso dito puntato con lo
sfondo cambiato. Non basta: un tono è uno stato d'animo, e uno stato
d'animo ha molti modi di manifestarsi. Qui ogni immagine ha un gesto,
una distanza fra i due e un rapporto di forze diversi.

Le azioni sono scritte per NON dipendere dal luogo: niente divani su cui
saltare o caffè da mescolare, perché la stessa azione deve reggere in
curva come in metropolitana.
"""

from __future__ import annotations

# Per ogni tono: l'aria generale, e sedici modi diversi di averla.
TONI: dict[str, tuple[str, list[str]]] = {
    "battibecco": (
        "I due litigano.",
        [
            "quello a sinistra punta l'indice contro l'altro con le sopracciglia abbassate e la vena del nervoso sulla tempia, quello a destra ha le braccia conserte e un sopracciglio alzato",
            "urlano tutti e due insieme a pochi centimetri di distanza, faccia a faccia, senza che nessuno dei due ascolti l'altro",
            "quello a sinistra si è girato di spalle offeso con le braccia incrociate, quello a destra gli parla alla nuca allargando le braccia esasperato",
            "quello a sinistra mostra lo schermo del telefono come se fosse una prova schiacciante, quello a destra lo scosta con il dorso della mano senza degnarlo di uno sguardo",
            "quello a sinistra applaude lentamente con un sorriso sarcastico e gli occhi socchiusi, quello a destra è paonazzo con le vene del nervoso sulla tempia",
            "si tengono per la manica tirandosi a vicenda, il corpo inclinato all'indietro come chi vorrebbe andarsene ma non ha finito di parlare",
            "quello a sinistra conta gli argomenti sulle dita di una mano con aria implacabile, quello a destra alza gli occhi al cielo con la testa rovesciata all'indietro",
            "quello a sinistra batte il pugno su un piano davanti a sé, quello a destra sussulta all'indietro con gli occhi spalancati",
            "sono fronte contro fronte, il collo teso e le mascelle serrate, come due allenatori a bordocampo",
            "quello a sinistra parla con la mano chiusa a pigna scuotendola, quello a destra rifà lo stesso gesto per prenderlo in giro",
            "quello a sinistra è seduto e alza le spalle con aria provocatoria, quello a destra sta in piedi sopra di lui a braccia spalancate",
            "si strappano di mano lo stesso oggetto tirandolo ognuno dalla propria parte, i denti stretti",
            "quello a sinistra si tappa le orecchie con le mani e chiude gli occhi, quello a destra continua a parlargli addosso indicandolo",
            "quello a sinistra indica con rabbia un punto fuori campo, quello a destra guarda in quella direzione con aria scettica e le braccia lungo i fianchi",
            "hanno tutti e due le braccia larghe e i palmi rivolti in su, in un identico gesto di «ma che vuoi da me»",
            "quello a sinistra tiene una mano sul petto dell'altro per tenerlo a distanza, quello a destra si sporge oltre la mano continuando a parlare",
        ],
    ),
    "esultanza": (
        "I due esultano.",
        [
            "hanno tutti e due i pugni al cielo e la bocca spalancata in un grido di gioia, gli occhi felici ad arco, con linee cinetiche a raggiera dietro di loro",
            "si abbracciano saltando con i piedi staccati da terra, le teste rovesciate all'indietro",
            "quello a sinistra si copre la faccia con tutte e due le mani per l'emozione, quello a destra lo indica ridendo a bocca spalancata",
            "battono il cinque in alto con il corpo inarcato e una gamba sollevata",
            "quello a sinistra si è tirato la maglietta sopra la testa come i calciatori dopo un gol, quello a destra ride piegato in due",
            "sono tutti e due in ginocchio con le braccia spalancate e gli occhi al cielo",
            "quello a sinistra batte le mani sopra la testa, quello a destra si morde il pugno chiuso per l'emozione",
            "si tengono per le spalle e si scuotono a vicenda, le teste che ciondolano e le bocche spalancate",
            "quello a sinistra ha le mani sulla testa e la bocca aperta, incredulo dalla gioia, quello a destra lo indica ridendo",
            "si stringono la mano con forza scuotendola, ridendo tutti e due a bocca spalancata",
            "quello a sinistra bacia la propria sciarpa azzurra tenendola con due mani, quello a destra alza il pugno accanto a lui",
            "quello a sinistra alza la sciarpa azzurra sopra la testa tesa fra le due mani, quello a destra ha le braccia al cielo",
            "mostrano tutti e due lo schermo del telefono verso l'alto come un trofeo, le bocche aperte",
            "quello a destra è issato sulle spalle di quello a sinistra con le braccia al cielo",
            "quello a sinistra abbraccia l'altro da dietro, tutti e due urlano nella stessa direzione con gli occhi chiusi",
            "quello a sinistra ha le braccia larghe con l'aria di chi l'aveva detto, quello a destra applaude con la testa che annuisce",
        ],
    ),
    "sconforto": (
        "I due sono affranti, con un retino verticale che cala dall'alto dietro di loro.",
        [
            "hanno tutti e due le mani nei capelli, le spalle basse e gli occhi piccoli e sconsolati",
            "quello a sinistra è accasciato in avanti con la faccia nelle mani, quello a destra gli appoggia una mano sulla spalla guardando altrove",
            "sono seduti tutti e due a testa bassa, immobili, lo sguardo puntato a terra",
            "quello a sinistra fissa il vuoto con gli occhi spenti, quello a destra si copre metà faccia con la sciarpa azzurra",
            "quello a sinistra si copre gli occhi con l'avambraccio, quello a destra guarda in alto con aria rassegnata e una grossa goccia di sudore sulla tempia",
            "sono crollati all'indietro tutti e due, le braccia penzoloni lungo i fianchi e la testa rovesciata",
            "quello a sinistra spegne uno schermo con un gesto lento e stanco, quello a destra non si è mosso di un centimetro",
            "quello a sinistra morde la sciarpa azzurra con gli occhi chiusi, quello a destra tira un calcio a vuoto",
            "quello a sinistra abbraccia l'altro per consolarlo, quello a destra resta rigido con le braccia lungo i fianchi",
            "hanno tutti e due la testa appoggiata alle mani, i gomiti puntati su un piano davanti a loro",
            "quello a sinistra si è alzato per andarsene dando le spalle, quello a destra resta fermo a fissare il nulla",
            "quello a sinistra si strofina gli occhi con il pollice e l'indice, quello a destra sospira con le guance gonfie",
            "guardano tutti e due verso il basso, quello a destra tiene la sciarpa azzurra che gli pende dalle mani fino a terra",
            "quello a sinistra ha la fronte appoggiata a una superficie verticale, quello a destra è dietro di lui con una mano sulla sua spalla",
            "sono seduti tutti e due di profilo sul bordo di qualcosa, le spalle curve e i gomiti sulle ginocchia",
            "quello a sinistra alza le braccia al cielo in una domanda muta, quello a destra scuote la testa con gli occhi chiusi",
        ],
    ),
    "complotto": (
        "I due complottano, con l'aria di chi sta dicendo una cosa che non deve sentire nessun altro.",
        [
            "quello a sinistra si copre la bocca con la mano e sussurra all'orecchio dell'altro con un sorriso furbo e un occhio socchiuso, quello a destra ascolta con gli occhi spalancati",
            "sono chini tutti e due a coppa sopra lo stesso telefono, e si guardano intorno con la coda dell'occhio",
            "quello a sinistra tira l'altro per il braccio in disparte, sbirciando alle proprie spalle",
            "hanno tutti e due l'indice sulle labbra e guardano in due direzioni opposte",
            "quello a sinistra si alza la sciarpa azzurra fin sotto gli occhi, quello a destra annuisce con aria d'intesa",
            "sono schiena contro schiena e si parlano di lato senza guardarsi, gli occhi che scattano ai lati",
            "quello a sinistra fa un cenno con il mento verso qualcosa fuori campo, quello a destra sgrana gli occhi",
            "sporgono solo con la testa e le spalle da dietro un angolo, uno sopra l'altro",
            "quello a sinistra mostra qualcosa che tiene nel palmo semichiuso, quello a destra si sporge a guardare con un sopracciglio alzato",
            "quello a sinistra ammicca con un occhio verso l'altro, quello a destra risponde con un sorriso di sbieco",
            "si coprono tutti e due la bocca con la mano e parlano insieme, le teste vicinissime",
            "quello a sinistra tiene l'altro per la spalla tirandoselo addosso, con un gran sorriso furbo",
            "quello a sinistra scrive sul telefono tenendolo basso e nascosto, quello a destra guarda in giro facendo da palo",
            "sono accovacciati vicini con le teste unite, le mani sulle ginocchia",
            "quello a sinistra sussurra da dietro la spalla dell'altro, guardano tutti e due dritti davanti a sé",
            "quello a sinistra si volta a controllare alle spalle mentre quello a destra parla velocemente muovendo le mani",
        ],
    ),
    "spiegone": (
        "Quello a sinistra sta spiegando qualcosa a chi non ha chiesto niente, e quello a destra lo subisce.",
        [
            "quello a sinistra ha l'indice alzato e gli occhi socchiusi da saccente, quello a destra lo guarda esausto con una goccia di sudore sulla tempia",
            "quello a sinistra disegna uno schema nell'aria con tutte e due le mani, quello a destra ha la testa appoggiata a una mano",
            "quello a sinistra conta i punti sulle dita arrivando al quarto, quello a destra guarda l'orologio al polso",
            "quello a sinistra tiene un foglio e ci batte sopra l'indice, quello a destra guarda ostentatamente da un'altra parte",
            "quello a sinistra gesticola largo con le braccia aperte, quello a destra si è addormentato in piedi con la testa ciondoloni",
            "quello a sinistra mostra uno schermo con delle forme astratte, quello a destra sbadiglia coprendosi appena la bocca",
            "quello a sinistra scandisce le parole con la mano a taglio, quello a destra si copre tutta la faccia con una mano",
            "quello a sinistra ha le braccia spalancate con l'aria di chi dice un'ovvietà, quello a destra alza gli occhi al cielo",
            "quello a sinistra si aggiusta il colletto con aria dotta e il mento alto, quello a destra ha le braccia abbandonate e lo sguardo vuoto",
            "quello a sinistra indica il cielo come una fonte di verità, quello a destra sta uscendo di lato dall'inquadratura",
            "quello a sinistra tiene l'altro per un braccio per non farlo scappare mentre continua a parlare, quello a destra è proteso verso l'uscita",
            "quello a sinistra traccia una linea con il dito su un piano davanti a sé, quello a destra guarda il vuoto con la testa fra le mani",
            "quello a sinistra alza due dita a indicare due punti, quello a destra alza una mano aperta per dire basta",
            "quello a sinistra parla guardando davanti a sé senza rivolgersi a nessuno, quello a destra dietro di lui fa il gesto della chiacchiera con la mano",
            "quello a sinistra mima uno schema muovendo le due mani come pedine, quello a destra guarda il telefono ignorandolo",
            "quello a sinistra batte l'indice sul palmo dell'altra mano a ogni parola, quello a destra ha la testa rovesciata all'indietro e gli occhi chiusi",
        ],
    ),
    "attesa": (
        "I due aspettano qualcosa che deve ancora succedere, e l'aria è tesa.",
        [
            "sono protesi in avanti e immobili, le mani giunte davanti alla bocca e gli occhi sgranati fissi su qualcosa fuori campo",
            "si mangiano tutti e due le unghie con lo sguardo fisso nella stessa direzione",
            "quello a sinistra cammina avanti e indietro con le mani sui fianchi, quello a destra è seduto e lo segue con gli occhi",
            "hanno tutti e due le mani giunte come in preghiera davanti al viso e gli occhi socchiusi",
            "quello a sinistra guarda l'orologio al polso, quello a destra guarda lo schermo del telefono, tutti e due immobili",
            "si tengono per un braccio, rigidi, senza guardarsi, lo sguardo puntato avanti",
            "quello a sinistra si copre metà faccia con la sciarpa azzurra e guarda con un occhio solo, quello a destra è immobile",
            "trattengono tutti e due il respiro con le guance gonfie e gli occhi spalancati",
            "quello a sinistra si sporge in avanti fin quasi a cadere, quello a destra lo trattiene per la maglietta",
            "stanno tutti e due dritti e rigidi come statue, le braccia lungo i fianchi e gli occhi fissi",
            "quello a sinistra tamburella le dita su un piano, quello a destra fa oscillare nervosamente una gamba",
            "hanno tutti e due gli occhi socchiusi a fessura, come chi non vuole guardare ma non riesce a smettere",
            "quello a sinistra chiude gli occhi e gira la testa dall'altra parte, quello a destra spalanca gli occhi e non si muove",
            "sono seduti tutti e due sull'orlo, la schiena dritta e le mani sulle ginocchia",
            "quello a sinistra strizza la sciarpa azzurra fra le mani, quello a destra si tiene la fronte",
            "guardano tutti e due verso l'alto nella stessa direzione, le bocche socchiuse e gli occhi grandi",
        ],
    ),
}

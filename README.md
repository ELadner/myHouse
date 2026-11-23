myHouse è un plugin di modellazione architettonica che permette di modellare con semplicità un abitazione
myHouse is an architectural modeling plugin that allows for the simple modeling of a home.

Nella versione 1.0 (settaggio piani - muri - solai - porte -finestre - pilastri - tetti - travi - scale - rampe - balaustre - recinsioni)
In version 1.0, it includes settings for: floors, walls, slabs, doors, windows, columns, roofs, beams, stairs, ramps, balustrades, and fences.

Il plugin è stato inserito tra le estensioni ufficiale quindi potrà essere anche scaricato direttamente dalle estensioni del programma oppure lo puoi scaricare qui sotto, se scaricandolo dalle estensioni vedi che la versione non è stata ancora aggiornata scaricalo da qui in quanto il caricamento nelle estensioni ufficiali avviene dopo qualche giorno

The plugin has been added to the official extensions, so it can be downloaded directly via the program's extensions menu; alternatively, you can download it below. If you find that the version in the official extensions hasn't been updated yet, please download it from here, as it can take a few days for updates to appear in the official extensions list.

## Novità di questo ramo / What's new in this branch

Modifiche rispetto alla versione 1.0. Il codice sorgente è ora anche nella cartella `myhouse/`; `myhouse.zip` contiene gli stessi file.
Changes on top of version 1.0. The source code is now also in the `myhouse/` folder; `myhouse.zip` holds the same files.

**Lingua e unità / Language and units**

- Interfaccia in più lingue: inglese e italiano inclusi; segue la lingua di IngeTrazo. Per aggiungere una lingua basta copiare `myhouse/i18n/it.json` in `<codice>.json` e tradurre i valori.
  Multilingual interface: English and Italian included; it follows IngeTrazo's language. To add a language, copy `myhouse/i18n/it.json` to `<code>.json` and translate the values.
- Misure in piedi e pollici oppure metriche: Estensioni > MyHouse > Unità… (segui il documento, piedi e pollici, metrico). Le misure proposte seguono le unità; il modello resta in metri.
  Sizes in feet and inches or metric: Extensions > MyHouse > Units… (follow the document, feet and inches, metric). The proposed sizes follow the units; the model is still stored in metres.

**Finestre / Windows**

- Finestre accoppiate: fino a 6 ante con montante fisso a "I"; anima, alette e profondità del canale si impostano separatamente.
  Mulled windows: up to 6 sashes with a fixed I-shaped mullion; web, flanges and channel depth are set independently.
- Misure standard americane per tipo di finestra (solo in piedi e pollici); si può sempre digitare una misura qualsiasi.
  US standard sizes by window type (feet and inches only); any size can still be typed.
- Durante la posa, Spazio cambia l'ancoraggio: sinistra, centro, destra.
  While placing, Space changes the anchor: left, middle, right.

**Porte / Doors**

- Larghezza e altezza sono quelle della porta (anta); il telaio sta all'esterno.
  Width and height are those of the door itself (the slab); the frame sits outside.
- Porte a libro per armadi, singole o doppie.
  Bi-fold closet doors, single or dual.
- Inverti porta (lato della maniglia): tasto destro su una porta posata, oppure R durante la posa.
  Reverse door (handle side): right-click a placed door, or R while placing.
- Durante la posa, Spazio cambia l'ancoraggio, come per le finestre.
  While placing, Space changes the anchor, as for windows.

**Muri / Walls**

- Ortogonale a passi di 45°.
  Ortho in 45° steps.
- Adotta muro: trasforma un gruppo esistente a forma di parallelepipedo in un muro MyHouse, così porte e finestre lo possono forare.
  Adopt wall: turns an existing box-shaped group into a MyHouse wall, so doors and windows can cut it.
- Allunga muro: sposta un'estremità con un clic o digitando la lunghezza; gli angoli collegati la seguono.
  Stretch wall: moves one end by click or typed length; joined corners follow.
- Dividi muro: taglia un muro in due nel punto del clic.
  Split wall: cuts a wall in two at the clicked point.
- Giunto tra muri: angolo a sghembo oppure di testa, con l'uno o l'altro muro passante.
  Wall joint: mitred or butt corner, with either wall running through.

**Altro / Other**

- La barra MyHouse si mostra da sola al primo avvio con IngeTrazo 0.6.3.
  The MyHouse toolbar shows itself on first start with IngeTrazo 0.6.3.

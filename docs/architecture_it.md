# Architettura e flussi di comunicazione

L'applicazione è composta da due processi Python con responsabilità distinte:

- `streamdock-n3.service` esegue il daemon. Gestisce la connessione USB HID, riceve gli eventi del dispositivo, aggiorna le immagini dei tasti e avvia le azioni configurate.
- `streamdock-n3-gui` è un'applicazione GTK separata. Modifica la configurazione dell'utente e, dopo il salvataggio, chiede a systemd di riavviare il daemon se il servizio è attivo.

Il daemon comunica con Stream Dock tramite due percorsi di input. Gli eventi di pulsanti e manopole arrivano attraverso l'SDK incluso nel progetto, usando USB HID/libusb. Alcune modalità del firmware espongono anche eventi dei tasti multimediali tramite Linux evdev; questo percorso viene letto separatamente e può essere acquisito quando sono configurate azioni corrispondenti. Gli aggiornamenti dello schermo tornano al dispositivo attraverso USB HID.

## Avvio del servizio e connessione al dispositivo

```mermaid
sequenceDiagram
    autonumber
    participant Systemd as systemd utente
    participant Daemon as daemon Python
    participant Config as configurazione XDG
    participant Terminal as rilevamento terminale
    participant Manager as DeviceManager SDK
    participant HID as LibUSBHIDAPI
    participant Dock as Stream Dock N3
    participant Reader as thread di lettura SDK
    participant Evdev as worker evdev

    Systemd->>Daemon: ExecStart streamdock-n3
    Daemon->>Config: load_normalized()
    Config-->>Daemon: pagine, tasti, azioni, terminale
    Daemon->>Terminal: risolvi il terminale se impostato su auto
    Terminal-->>Daemon: ID del terminale rilevato
    Daemon->>Config: salva il terminale rilevato se è cambiato
    Daemon->>Manager: cerca dispositivi VID/PID supportati
    Manager->>HID: enumerate_devices(vendor_id, product_id)
    HID->>Dock: cerca interfacce USB HID
    Dock-->>HID: percorso e metadati del dispositivo trovato
    HID-->>Manager: informazioni sul dispositivo
    Manager-->>Daemon: istanza StreamDockN3
    Daemon->>HID: apre il percorso del dispositivo
    HID-->>Reader: avvia il thread asincrono di lettura HID
    HID-->>Dock: heartbeat periodico
    Daemon->>Dock: inizializza e imposta la luminosità
    loop Ogni tasto LCD della pagina corrente
        Daemon->>Dock: genera o carica l'immagine e chiama set_key_image()
        Dock-->>Daemon: esito del trasferimento dell'immagine
    end
    Daemon->>Reader: registra il callback on_input
    Daemon->>Evdev: avvia il worker con azioni e terminale selezionato
    Evdev->>Evdev: cerca i dispositivi Stream Dock in /dev/input/event*
    opt grab_evdev attivo e azioni evdev configurate
        Evdev->>Evdev: acquisisce i dispositivi di input corrispondenti con EVIOCGRAB
    end
```

`DeviceManager` crea un trasporto `LibUSBHIDAPI` specifico per ogni dispositivo trovato. L'apertura del dispositivo SDK avvia i thread di lettura e heartbeat. Il daemon inizializza quindi l'N3, disegna la pagina corrente, registra il callback e avvia il worker evdev indipendente.

## Input del dispositivo e avvio delle azioni

```mermaid
sequenceDiagram
    autonumber
    participant Dock as Stream Dock N3
    participant HID as trasporto USB HID
    participant Reader as thread di lettura SDK
    participant Daemon as daemon Python
    participant Evdev as worker evdev
    participant Config as configurazione e azioni XDG
    participant Terminal as terminale selezionato
    participant Shell as shell dei comandi
    participant App as applicazione o xdg-open

    alt Evento di pulsante o manopola via USB HID
        Dock->>HID: report di input HID
        HID->>Reader: read_() restituisce i byte del report
        Reader->>Reader: decode_input_event()
        Reader->>Daemon: on_input(device, InputEvent)
        Daemon->>Daemon: event_key() associa l'evento a una chiave di configurazione
    else Evento di tasto multimediale via Linux evdev
        Dock->>Evdev: evento del kernel in /dev/input/event*
        Evdev->>Evdev: select(), read(), mappatura event_key
        Evdev->>Daemon: avvia l'azione associata
    end

    alt Azione di navigazione tra pagine
        Daemon->>Daemon: aggiorna la pagina corrente e la mappa delle azioni
        Daemon->>HID: genera e invia le nuove immagini dei tasti
        HID->>Dock: report delle immagini e aggiornamento dello schermo
    else Azione configurata
        Daemon->>Config: risolve l'ID di riferimento, se è una copia di un modello
        Config-->>Daemon: definizione dell'azione dalla cartella delle azioni utente
        Daemon->>Daemon: valida e avvia il tipo di azione
        alt Azione shell con output abilitato
            Daemon->>Terminal: avvia il terminale selezionato con cwd e comando
            Terminal->>Shell: esegue il comando
            Shell-->>Terminal: stdout, stderr e codice di uscita
            Note over Terminal: L'output resta visibile finché l'utente non chiude il terminale
        else Azione shell senza output
            Daemon->>Shell: avvia il comando in background e scarta stdout/stderr
        else Avvio di un'applicazione o apertura di un URL
            Daemon->>App: Popen(argv, shell=False)
        else Azione sequenziale
            Daemon->>Daemon: avvia il primo passaggio e programma i successivi con Timer
        end
    end
```

Gli eventi HID vengono decodificati dal thread di lettura SDK prima di raggiungere il callback del daemon. Gli eventi evdev non passano da quel decoder: il worker mappa separatamente i codici dei tasti Linux e usa lo stesso dispatcher delle azioni. Per un'azione shell con `show_output`, il terminale selezionato esegue il comando in una shell; stdout e stderr vengono quindi mostrati nel terminale e non in una finestra GTK.

## Configurazione GUI e riavvio del servizio

```mermaid
sequenceDiagram
    autonumber
    actor User as Utente
    participant GUI as applicazione GTK
    participant Config as file di configurazione XDG
    participant Systemd as systemd utente
    participant Daemon as daemon Python
    participant Dock as Stream Dock N3

    User->>GUI: avvia streamdock-n3-gui
    GUI->>Config: load_normalized(config.json)
    Config-->>GUI: pagine, azioni, terminale selezionato
    GUI->>GUI: rileva i terminali installati per il selettore
    User->>GUI: seleziona un terminale o modifica un'azione di un tasto
    opt Crea un'azione da un modello
        GUI->>Config: copia il modello nella cartella delle azioni utente usando il suo ID
        GUI->>Config: copia l'icona del modello in actions/assets/
        GUI->>Config: salva il riferimento all'azione sul tasto selezionato
    end
    User->>GUI: preme Salva
    GUI->>Config: scrive config.json in modo atomico
    opt Il servizio daemon è attivo
        GUI->>Systemd: systemctl --user restart streamdock-n3.service
        Systemd->>Daemon: arresta il processo precedente e avvia quello nuovo
        Daemon->>Config: ricarica configurazione e definizioni delle azioni
        Daemon->>Dock: riconnette, inizializza e applica la pagina corrente
        Systemd-->>GUI: esito del riavvio
        GUI-->>User: mostra l'esito del salvataggio e del riavvio
    end
```

La GUI non apre né controlla direttamente il dispositivo USB. Scrive i file di configurazione e delle azioni dell'utente; il daemon è l'unico processo che gestisce la connessione al dispositivo. I modelli di azione vengono copiati nella cartella XDG dell'utente, così le modifiche personali non alterano i modelli inclusi nel pacchetto.

## Codice correlato

- [Ciclo di vita del daemon e avvio delle azioni](../src/streamdock_n3/daemon.py)
- [Rilevamento dei terminali e avvio dei comandi](../src/streamdock_n3/terminals.py)
- [Caricamento della configurazione, migrazione e riferimenti alle azioni](../src/streamdock_n3/config.py)
- [GUI e integrazione con systemd](../src/streamdock_n3/gui.py)
- [Rilevamento dei dispositivi incluso nel progetto](../src/streamdock_n3/_vendor/StreamDock/DeviceManager.py)
- [Unità di servizio Stream Dock](../src/streamdock_n3/_data/streamdock-n3.service)
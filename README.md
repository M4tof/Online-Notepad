# Temat: Online Notepad 
 `Grupowy edytor plików tekstowych`
 
 Projekt obejmuje dwa programy, serwer TCP napisany w C++ dla systemu operacyjnego Linux oraz klienta TCP napisanego w Pythonie dla systemu Windows.

## Opis Protokołu Komunikacji

Komunikacja między klientem a serwerem opiera się na protokole TCP. Wymieniane dane są w formacie tekstowym, gdzie każda wiadomość w głównej pętli jest identyfikowana przez typ operacji (np. `1`, `2`, `3`, `4`), a pozostałe części wiadomości są podzielone za pomocą separatorów `.` i `|`.  

Przykładowe wiadomości:  
- `1.X1.Y1.X2.Y2.text` – Reprezentuje zmianę w pliku tekstowym od pozycji `(X1.Y1)` do `(X2.Y2)` z treścią `text`.  
- `2.username` – Powiadomienie o nowym użytkowniku.  
- `2.username1|username2|username3` - Lista użytkowników połączonych z plikiem.
- `3.username` – Informacja o użytkowniku rozłączającym się z serwerem.  
- `4.Int` - Sygnał o rozpoczęciu procesu synchronizacji danych między kopiami plików. Następnie nadesłane zostanie Int linijek zawierających dane z głównej kopii.

Pierwsza wymiana informacji po połączeniu służy do synchronizacji lokalnej kopii pliku z główną kopią serwera i przebiega następująco:

- [Klient -> Serwer] `nazwaPliku.rozszerzenie|username` np. File.txt|KMan
- [Serwer -> Klient] `Int N` Liczba linii w głównej kopii pliku np. 200
- [Serwer -> Klient] `Zawartość N-tej Linii` np. Przykładowy tekst.|do końca danej linii.\n

Następnie serwer aktualizuje lokalną listę użytkowników i przesyła ją do wszystkich klientów połączonych z tym plikiem.
W tym momencie klient i wątek serwera dla tego klienta są gotowe na wymianę danych przez wiadomości typu `1` , `2` oraz `3` i `4`

## Opis Implementacji

### Serwer:

Kod źródłowy serwera zawarty został w pliku server.cpp.

**Najważniejsze komponenty i funkcjonalności serwera:**
#### 1. Nasłuchiwanie połączeń
Serwer działa w sposób współbieżny z wykorzystaniem mechanizmu podprocesów. Po zaakceptowaniu połączenia proces wykonuje forka, a obsługą klienta zajmuje się proces dziecko, podczas gdy proces macierzysty wraca do przechwytywania połączeń.

#### 2. Powiązanie z plikiem
Komunikacja z klientem odbywa się przy użyciu ramek z odpowiednio etykietowaną zawartością tesktową. W plikach lokalnych na serwerze przechowywane są kopie wszystkich wcześniej edytowanych plików. Po nawiązaniu połączenia z klientem serwer przesyła zawartość całego pliku dokonując zapisów na deskryptor klienta linijka po linijce.

#### 3. Kolejki komunikatów
Otrzymawszy od klienta nazwę żądanego przez niego pliku wygenerowana zostaje kolejka komunikatów z kluczem unikalnym dla nazwy danego pliku (przy użyciu funkcji `msgget`). W ten sposób wszystkie podprocesy obsługujące klientów pracujących nad tym samym plikiem mogą wysyłać między sobą komunikaty, co pozwala np. na poinformowanie pozostałych klientów o dołączeniu nowego użytkownika pracującego nad danym plikiem.

#### 4. Odbieranie edycji
Serwer na bieżąco odbiera od klientów informacje o edycjach dokonanych w aplikacjach klientów i zapewnia poinformowanie wszystkich pozostałych podłączonych klientów o edycjach dokonanych przez jednego z nich, jak i również uwzględnienie dokonanych zmian w kopii lokalnej.

#### 5. Synchronizacja
Aby uniknąć rozbieżności między wersjami lokalnymi pliku u poszczególnych klientów, co może wynikać np. z opóźnień w otrzymywaniu pakietów, co określony czas serwer przesyła klientowi lokalną wersję pliku, która nadpisuje zawartość pliku klienta.

### Klient:  

Działanie klienta jest podzielone na dwa pliki:  
1. **`main.py`** – Główny plik odpowiedzialny za implementację klienta, w tym logikę aplikacji oraz interfejs graficzny.  
2. **`settings.json`** – Plik konfiguracyjny przechowujący dane połączenia (adres IP, port serwera) oraz ostatnio używaną nazwę użytkownika.  

**Najważniejsze komponenty i funkcjonalności klienta:** 
#### 1. Interfejs Graficzny  
Interfejs został stworzony przy użyciu biblioteki `tkinter`. Klient zawiera:  
- **Pole tekstowe** (`text_widget`), w którym użytkownik może edytować zawartość pliku.  
- **Listę użytkowników** (`users_listbox`) wyświetlającą aktualnie podłączonych użytkowników.  
- Menu umożliwiające zarządzanie ustawieniami połączenia, zmianą nazwy użytkownika oraz otwieraniem lokalnych plików.

#### 2. Kolejki Komunikacyjne  
Klient wykorzystuje dwie kolejki komunikacyjne (`queue.Queue`) do asynchronicznej wymiany danych między wątkami:  
- **`to_server_queue`** – Kolejka przechowująca zmiany wprowadzone lokalnie, które mają zostać wysłane do serwera.  
- **`from_server_queue`** – Kolejka zawierająca dane odebrane od serwera, które zostaną przetworzone przez interfejs graficzny.

#### 3. Tworzenie Połączenia  
Połączenie z serwerem jest zarządzane w osobnym wątku TCP (`tcp_thread`), co zapewnia płynność działania interfejsu graficznego oraz brak blokowania od strony połączenia.  

**Proces połączenia:**  
1. Po wybraniu adresu serwera i portu, klient wysyła nazwę pliku oraz nazwę użytkownika w wiadomości inicjalnej.  
2. Serwer odsyła zawartość głównej kopii pliku oraz liczbę linii.  
3. Po synchronizacji pliku lokalnego z serwerem, klient zaczyna dwukierunkową komunikację:  
   - Odbiera wiadomości o zmianach wprowadzonych przez innych użytkowników.  
   - Wysyła zmiany lokalne zapisane w `to_server_queue`.  

#### 4. Zarządzanie Zmianami w Tekście  
Zmiany wprowadzone w polu tekstowym są monitorowane za pomocą zdarzeń klawiatury i myszy (`<KeyRelease>` oraz `<ButtonRelease>`). Wiadomość o zmianie pliku jest zawsze wysyłana jako kontekst między dwoma takimi zdarzeniami dzięki czemu akcje takie jak wycinanie, wklejanie i usuwanie także działają.

**Mechanizm wykrywania zmian:**  
- W każdej chwili przechowywana jest pozycja kursora (`PREV_CURSOR_POSITION`) oraz punkt początkowy zmian (`START_CURSOR_POSITION`).  
- Gdy użytkownik zmodyfikuje tekst, zmiana jest obliczana na podstawie pozycji początkowej i końcowej w formacie `X1.Y1` i `X2.Y2`.  
- Fragment tekstu, który został zmieniony, jest wysyłany do serwera w formacie:  
`1.X1.Y1.X2.Y2.text`
- Zmiany od innych użytkowników są odbierane, przetwarzane i wprowadzane w polu tekstowym w odpowiednich miejscach.

#### 5. Obsługa Użytkowników  
Klient synchronizuje listę użytkowników z serwerem:  
- Nowy użytkownik jest dodawany na liście (`2.username`).  
- Rozłączenie użytkownika jest obsługiwane przez wysłanie wiadomości `3.username` przed zamknięciem aplikacji.

#### 6. Obsłga Synchronizacji Plików
Po odebraniu sygnału zaczynającego synchronizację Klient przełącza działanie, odczytuje n linii a następnie na ich bazie odtwarza główną kopię pliku.


## Kompilacja
- **Serwer:**  
`g++ -Wall server.cpp -o server`

- **Klient:**  
Nie wymaga kompilacji.

## Uruchomienie 
- **Serwer:**  
Uruchomienie skompilowanego pliku źródłowego (nazwa server).  
- **Klient:**  
Uruchomienie pliku `main.py` znajdującego się w folderze `Frontend`.  

## Obsługa  
- **Serwer:**  
Wystarczy uruchomić.  

- **Klient:**  
1. **Pierwsze uruchomienie** wymaga skonfigurowania adresu połączenia i opcjonalnie zmiany nazwy użytkownika na inną niż `Guest`. Przy kolejnych uruchomieniach dane z poprzedniej sesji są automatycznie wczytywane z pliku ustawień `settings.json`
2. **Dodanie adresu serwera:**  
   - `[Online Settings - Manage Addresses]` – Użytkownik może dodać nowy adres, podając nazwę (dowolną), adres IP oraz port serwera.  
3. **Zmiana nazwy użytkownika {OPCJONALNIE}:**  
   - `[Online Settings - Change Username]` – Użytkownik może zmienić nazwę. Nazwa użytkownika nie może zawierać znaków `.` ani `|`.  
4. **Otwieranie plików:**  
   - `[File - Open]` – Użytkownik wybiera lokalny plik (lub tworzy nowy), który musi mieć nazwę i rozszerzenie zgodną z plikiem do którego chce się dostać.  
5. **Połączenie z serwerem:**  
   - `[Online Settings - Connect to Address]` – Klient synchronizuje lokalną kopię z główną kopią pliku na serwerze i rozpoczyna komunikację dwustronną. 
6. **Rozłączenie:**  
   - Zamknięcie programu za pomocą przycisku systemowego `X`.
  

## Autorzy
 - inf155939 - Krzysztof Mańczak
 - 

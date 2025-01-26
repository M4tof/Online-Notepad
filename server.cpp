#include <stdio.h>
#include <iostream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <vector>
#include <fstream>
#include <signal.h>
#include <string>
#include <sys/ipc.h>
#include <sys/msg.h>
#include <mutex>
#include <chrono>
#include <fcntl.h>
#include <map>
#include "json.hpp"
#include <boost/interprocess/managed_shared_memory.hpp>
#include <boost/interprocess/containers/map.hpp>
#include <boost/interprocess/allocators/allocator.hpp>

#define SLEEPTIME 5000

int MAXIMUM = 10;
int limit = 0;

namespace bip = boost::interprocess;

typedef bip::allocator<std::pair<const std::string, int>, bip::managed_shared_memory::segment_manager> ShmemAllocator;
typedef bip::map<std::string, int, std::less<std::string>, ShmemAllocator> SharedMap;

std::mutex mtx;

struct message
{
    long mtype;
    char mtext[4096];
};

bool is_empty(std::ifstream &pFile) // zwróć true jeśli plik jest pusty, wpp zwróć false
{
    return pFile.peek() == std::ifstream::traits_type::eof();
}

int add_table(const std::string filename, std::vector<std::string> &text_arr) // sczytywanie z pliku o określonej nazwie wektora zawierającego stringi z poszczególnymi linijkami
{
    std::ifstream fin(filename);
    if (!fin)
        return -1; //-1 oznacza problem z czytaniem pliku
    if (!is_empty(fin))
    {
        nlohmann::json j = nlohmann::json::parse(fin);
        text_arr = j["vector"];
    }
    else
    {
        text_arr.push_back("");
    }
    fin.close();
    return 0;
}

void save_table(std::vector<std::string> &text_arr, char *filename)
{
    mtx.lock();
    std::ofstream fout(filename);
    nlohmann::json j;
    j["vector"] = text_arr;
    fout << j;
    fout.close();
    mtx.unlock();
}

int change_table(std::string update_message, std::vector<std::string> &text_arr, char *filename)
{
    int first = update_message.find('.', 2);
    int y1 = atoi(update_message.substr(2, first - 1).c_str()) - 1;
    int second = update_message.find('.', first + 1);
    int x1 = atoi(update_message.substr(first + 1, second - 1).c_str());
    int third = update_message.find('.', second + 1);
    int y2 = atoi(update_message.substr(second + 1, third - 1).c_str()) - 1;
    int fourth = update_message.find('.', third + 1);
    int x2 = atoi(update_message.substr(third + 1, fourth - 1).c_str());
    std::string content = update_message.substr(fourth + 1);
    if (content == "")
    {
        int column = x2;
        int line = y2;
        if(line > y1 && x2 == 0)
        {
            std::string col = text_arr[line];
            if(text_arr[y1][text_arr[y1].size()-1] == '\n')
                text_arr[y1] = text_arr[y1].substr(0, text_arr[y1].size()-1);
            text_arr[y1] += col;
            while(line > y1)
            {
                text_arr.erase(text_arr.begin() + line);
                line--;
            }
        }
        else
        {
            while (line > y1)
            {
                text_arr[line].erase(0, column);
                column = text_arr[line - 1].size() - 1;
                if (text_arr[line].size() > 1)
                {
                    text_arr[line - 1].insert(column, text_arr[line].substr(0, text_arr[line].size() - 1));
                    text_arr.erase(text_arr.begin() + line);
                }
                line--;
            }
            text_arr[line].erase(x1, column - x1);
        }
        
    }
    else if(y2 == y1)
    {
        text_arr[y2] = content;
    }
    else if (std::count(content.begin(), content.end(), '\n') == y2 - y1)
    {
        size_t last = content.find_last_of('\n');
        if (last == std::string::npos)
            last = -1;
        std::string last_line = last != content.size() ? content.substr(last + 1) : "";

        if (((int)last_line.size() == x2 && y2 - y1 > 0) || ((int)last_line.size() == x2 - x1 && y2 == y1))
        {
            int i = 0, line = y1, column = x1;
            while (i < (int)content.size())
            {
                text_arr[line].insert(text_arr[line].begin() + column, content[i]);
                column++;
                if (content[i] == '\n')
                {
                    if (column < (int)text_arr[line].size())
                    {
                        std::string rest = text_arr[line].substr(column);
                        text_arr.insert(text_arr.begin() + line + 1, rest);
                        text_arr[line].erase(column);
                        line++;
                        column = 0;
                    }
                    else
                    {
                        text_arr.insert(text_arr.begin() + line + 1, "");
                        line++;
                        column = 0;
                    }
                }
                i++;
            }
        }
    }
    return 0;
}

void sigchld_handler(int signo)
{
    wait(NULL);
    limit--;
}

int _read(int sfd, char *buf, int bufsize)
{
    int i, rc = 0;
    do
    {
        i = read(sfd, buf, bufsize);
        if (i < 0)
            return i;
        bufsize -= i;
        buf += i;
        rc += i;
    } while (*(buf - 1) != '\n');
    return rc;
}

void splitChar(const char *text, char *text1, char *text2) // funkcja do rozbijania ciągu znaków na dwa podciągi, rozdzielone w oryginalnym ciągu przez znak specjalny '|'
{
    // Pętla kopiuje wszystkie znaki z `text` do `text1` aż do:
    // - napotkania znaku końca ciągu (`'\0'`)
    // - lub separatora (`'|'`).
    for (; *text != '\0' && *text != '|';)
        *text1++ = *text++; // Przypisz bieżący znak do `text1` i przejdź do następnego
    *text1 = '\0';          // Dodaj znak końca ciągu do `text1`
    // Jeśli `|` został znaleziony, `text` teraz wskazuje na ten znak.
    // Pomijamy separator i kopiujemy resztę ciągu do `text2`.
    for (; *++text != '\0';) // Przesuń wskaźnik `text` i kontynuuj kopiowanie
        *text2++ = *text;
    *text2 = '\0'; // Dodaj znak końca ciągu do `text2`
}

void cleanup()
{
    // czyszczenie obiektów współdzielonych z pamięci
    bip::shared_memory_object::remove("SharedMemory");
    std::cout << "Shared memory cleaned up." << std::endl;
}

// Funkcja obsługująca sygnał, napisana by naciśnięcie ctrl+c powodowało wyczyszczenie pamięci
void sigint_handler(int signal)
{
    if (signal == SIGINT)
    {
        std::cout << "Caught SIGINT (Ctrl+C), cleaning up..." << std::endl;
        cleanup();
        exit(0); // Zakończenie programu
    }
}

int main()
{
    socklen_t sl;
    int on = 1;
    char buf[4096];
    int sfd, cfd;
    struct sockaddr_in saddr, caddr;

    bip::managed_shared_memory segment(bip::open_or_create, "SharedMemory", 65536);

    SharedMap *map = segment.find_or_construct<SharedMap>("SharedMap")(std::less<std::string>(), segment.get_allocator<SharedMap>());

    signal(SIGCHLD, sigchld_handler);
    signal(SIGINT, sigint_handler);

    saddr.sin_family = AF_INET;
    saddr.sin_addr.s_addr = INADDR_ANY;
    saddr.sin_port = htons(1234);
    sfd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    setsockopt(sfd, SOL_SOCKET, SO_REUSEADDR, (char *)&on, sizeof(on));
    bind(sfd, (struct sockaddr *)&saddr, sizeof(saddr));
    listen(sfd, 10);
    printf("The server has booted up, listening on port 1234\n");
    while (1)
    {
        sl = sizeof(caddr);
        while (limit >= MAXIMUM)
            sleep(1);
        cfd = accept(sfd, (struct sockaddr *)&caddr, &sl);
        limit++;
        if (!fork())
        {
            printf("New connection\n");
            close(sfd);

            char filename[4096], username[4096];
            read(cfd, buf, sizeof(buf));

            splitChar(buf, filename, username);
            printf("Received connection to file: %s from user %s\n", filename, username);
            if (map->find((std::string)filename) == map->end()) // jeśli pliku nie znaleziono, to go stwórz a w liczbie użytkowników wstaw 1
            {
                map->insert(std::make_pair((std::string)filename, 1));
                std::ofstream fout((std::string)filename, std::ios::app);
                fout.close();
                printf("Number of clients connected to %s is: %d", filename, map->find((std::string)filename)->second);
            }
            else // w przeciwnym wypadku inkrementuj liczbę użytkowników
            {
                map->find((std::string)filename)->second++;
                printf("Number of clients connected to %s is: %d", filename, map->find((std::string)filename)->second);
            }
            printf("\n");

            std::vector<std::string> text_arr;
            if (add_table(filename, text_arr) == -1) // pobieranie do wektora treści pliku
            {
                printf("There was a problem fetching a file data!\n");
            }

            key_t key;
            int msgid;

            // generacja klucza unikalnego dla danej nazwy pliku
            key = ftok(filename, 65);
            msgid = msgget(key, 0666 | IPC_CREAT | IPC_EXCL);
            if (msgid == -1)
            {
                if (errno == EEXIST)
                {
                    msgid = msgget(key, 0666);
                    if (msgid == -1)
                    {
                        perror("msgget");
                        exit(EXIT_FAILURE);
                    }
                }
                else
                {
                    perror("msgget");
                    exit(EXIT_FAILURE);
                }
            }

            // mtype: 1 dla normalnej komunikacji między procesami, 2 w przypadku dołączenia nowego użytkownika, 3 po rozłączeniu użytkownika, 8 na odpowiedzi z nazwą użytkownika dla nowych klientów
            message msg;
            msg.mtype = 2;
            while (msgrcv(msgid, &msg, sizeof(msg.mtext), 8, IPC_NOWAIT) != -1)
                ;
            memcpy(&msg.mtext, &username, sizeof(username));
            for (int i = 0; i < map->find((std::string)filename)->second - 1; i++) // wyślij użytkownikom informacje o nowym kliencie
                msgsnd(msgid, &msg, sizeof(msg.mtext), 0);
            int filled_lines=0;
            for(int i=0; i<(int)text_arr.size(); i++)
                if((text_arr[i].compare("")) != 0)
                    filled_lines++;
            printf("The accessed file has: %d lines\n", filled_lines);
            char const *pchar = std::to_string(filled_lines).c_str(); // wysyłanie rozmiaru wektora klientowi, by oczekiwał tylu wiadomości z wierszami
            write(cfd, pchar, strlen(pchar));
            usleep(SLEEPTIME);
            for (int i = 0; i < filled_lines; i++)
            {
                // text_arr[i].push_back('\n'); //jeśli klient ma problemy z wyświetlaniem bez dodanego \n
                write(cfd, text_arr[i].c_str(), strlen(text_arr[i].c_str()));
                usleep(SLEEPTIME/((int)text_arr.size()*10));
            }
            message cursor, new_user; // cursor przechowuje aktualną tablicę nazw podpiętych użytkowników, new_user do przechwytywania nowych klientów
            int i = 0;
            if (map->find((std::string)filename)->second > 1) // jeśli pod danym plikiem podpiętych jest >1 użytkowników
            {
                // zbieranie komunikatów o nazwach użytkowników od pozostałych klientów
                auto start = std::chrono::high_resolution_clock::now();
                auto stop = std::chrono::high_resolution_clock::now();
                auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(stop - start); // odmierzanie czasu jaki minął od początku zbierania
                while (i < map->find((std::string)filename)->second - 1 && duration.count() < 100)   // timeout 100ms, po tym czasie czekanie na inne nazwy użytkowników nie ma sensu
                {
                    if (msgrcv(msgid, &cursor, sizeof(cursor.mtext), 8, IPC_NOWAIT) != -1) // jeżeli otrzymano komunikat
                    {
                        if (strcmp(cursor.mtext, username) != 0) // mechanizm bezpieczeństwa na wypadek gdyby na liście miał znaleźć się sam klient (w poprawnie działającym programie nie powinno to wystąpić)
                        {
                            i++;
                            printf("Process %s has received answer %s from some process\n", username, cursor.mtext);
                            usleep(SLEEPTIME/((int)text_arr.size()*10));
                            // wysyłana jest pełna lista użytkowników pobrana od innego podprocesu serwera, który dołączył już nazwę użytkownika tego klienta
                            write(cfd, ("2." + (std::string)cursor.mtext).c_str(), strlen(cursor.mtext) + 2);
                        }
                    }
                    else if (errno != ENOMSG)
                    {
                        perror("msgrcv");
                    }
                    stop = std::chrono::high_resolution_clock::now();
                    duration = std::chrono::duration_cast<std::chrono::milliseconds>(stop - start); // ponowne odmierzanie czasu
                }
            }
            else
            {
                memcpy(&cursor.mtext, &username, sizeof(username));
                printf("User %s is the only one in file %s!\n", cursor.mtext, filename);
                // wysyłana jest klientowi lista zawierająca tylko jego nazwę użytkownika
                write(cfd, ("2." + (std::string)cursor.mtext).c_str(), strlen(cursor.mtext) + 2);
            }
            printf("The wait of %s is over!\n", username);
            bool isConnected = true;
            while (msgrcv(msgid, &msg, sizeof(msg.mtext), 1, IPC_NOWAIT) != -1) // w razie próby odczytu starych nieodczytanych komunikatów nieskierowanych do niego
                ;
            while (msgrcv(msgid, &msg, sizeof(msg.mtext), 2, IPC_NOWAIT) != -1)
                ;
            fcntl(cfd, F_SETFL, O_NONBLOCK);
            auto start = std::chrono::high_resolution_clock::now();
            auto stop = std::chrono::high_resolution_clock::now();
            auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(stop - start);
            while (isConnected) // todo: check if there's a better way to check if a user is still connected
            {
                // program sprawdza czy read() od klienta czeka na odczytanie oraz czy nie wystawiony został komunikat do msgrcv()
                if (msgrcv(msgid, &msg, sizeof(msg.mtext), 1, IPC_NOWAIT) != -1)
                {
                    // do debugu
                    printf("klient %s otrzyma: %s\n", username, msg.mtext);
                    // zaktualizuj lokalnie wektor z tekstem na podstawie zmian
                    change_table((std::string)msg.mtext, text_arr, filename);
                    // wyślij klientowi aktualizację tekstu z przedrostkiem 1. celem identyfikacji normalnej edycji
                    write(cfd, ((std::string)msg.mtext).c_str(), strlen(msg.mtext));
                    memset(&msg.mtext, 0, sizeof(msg.mtext));
                    usleep(SLEEPTIME);
                }
                if (msgrcv(msgid, &new_user, sizeof(new_user.mtext), 2, IPC_NOWAIT) != -1) // todo: wysyłanie klientowi zaktualizowanej o nowego użytkownika listy klientów i przesyłanie nowemu klientowi listy użytkowników zaktualizowanej o niego
                {
                    if (strcmp(new_user.mtext, ("2." + (std::string)username).c_str()) != 0) // mechanizm bezpieczeństwa przed próbą odczytania siebie samego
                    {
                        printf("User %s received announcement from %s while their list was %s\n", username, new_user.mtext, cursor.mtext);
                        // schemat listy: user1|user2|user3
                        memcpy(&cursor.mtext, ((std::string)cursor.mtext + "|" + (std::string)new_user.mtext).c_str(), strlen(((std::string)cursor.mtext + "|" + (std::string)new_user.mtext).c_str()));
                        cursor.mtype = 8;
                        printf("Updated %s list is now %s\n", username, cursor.mtext);
                        msgsnd(msgid, &cursor, sizeof(cursor.mtext), 0);
                        // wysyłanie z przedrostkiem 2. sugeruje aktualizację listy użytkowników u klienta
                        write(cfd, ("2." + (std::string)cursor.mtext).c_str(), strlen(cursor.mtext)+2);
                    }
                    usleep(SLEEPTIME);
                }
                if (msgrcv(msgid, &new_user, sizeof(new_user.mtext), 3, IPC_NOWAIT) != -1) // usuwanie użytkownika o danej nazwie z listy aktywnych użytkowników
                {
                    // znajdowanie użytkownika o podanej nazwie na liście i usuwanie go z niej
                    std::string new_cursor;
                    size_t start=0, end;
                    while((end = ((std::string)cursor.mtext).find('|', start)) != std::string::npos)
                    {
                        std::string curr = ((std::string)cursor.mtext).substr(start, end-start);
                        if(curr != (std::string)new_user.mtext)
                        {
                            if(!new_cursor.empty())
                                new_cursor += "|";
                            new_cursor += curr;
                        }
                        start = end + 1;
                    }
                    std::string last = ((std::string)cursor.mtext).substr(start);
                    if(!last.empty()  && last != (std::string)new_user.mtext)
                    {
                        if(!new_cursor.empty())
                            new_cursor += "|";
                        new_cursor += last;
                    }
                    
                    // wstawianie zaktualizowanej listy do cursora
                    memset(&cursor.mtext, 0, sizeof(cursor.mtext));
                    memcpy(&cursor.mtext, new_cursor.c_str(), strlen(new_cursor.c_str()));
                    // wysyłanie zaktualizowanej listy do klienta, również z przedrostkiem 2.
                    write(cfd, ("2." + (std::string)cursor.mtext).c_str(), strlen(cursor.mtext) + 2);
                }
                // czytanie połączenia z klientem celem sprawdzenia czy nie przesłał edycji, a potem przesłanie jej innym klientom
                fd_set readFds;
                FD_ZERO(&readFds);
                FD_SET(cfd, &readFds);
                timeval timeout{};
                timeout.tv_sec = 0;
                timeout.tv_usec = 10000; // 10 ms timeout
                int activity = select(cfd + 1, &readFds, nullptr, nullptr, &timeout);
                if (activity > 0 && FD_ISSET(cfd, &readFds))
                {
                    ssize_t bytesRead = recv(cfd, msg.mtext, sizeof(msg.mtext), 0); // odczytano od klienta
                    if (bytesRead > 0)
                    {
                        printf("Received from socket: %s (bytes: %d) \n", msg.mtext, (int)strlen(msg.mtext));
                        //todo: jesli wiadomosc od klienta zaczyna sie od 3. rozpocznij procedure rozlaczania sie
                        if(msg.mtext[0] == '3')
                        {
                            printf("Client disconnected\n");
                            memcpy(&cursor.mtext, &username, strlen(username));
                            msg.mtype = 3;
                            // prześlij nazwę rozłączonego klienta pozostałym klientom, aby usunęły go ze swoich list
                            for (int i = 0; i < map->find((std::string)filename)->second - 1; i++)
                                msgsnd(msgid, &msg, sizeof(msg.mtext), 0);
                            // zakończ odbieranie danych dla tego procesu
                            isConnected = false;
                        }
                        else
                        {
                            // zmień u siebie tablicę i rozpropaguj zmianę do klientów
                            change_table((std::string)msg.mtext, text_arr, filename);
                            save_table(text_arr, filename);
                            msg.mtype=1;
                            for (int i = 0; i < map->find((std::string)filename)->second - 1; i++)
                                msgsnd(msgid, &msg, sizeof(msg.mtext), 0);
                            memset(&msg.mtext, 0, sizeof(msg.mtext));
                        }
                    }
                    else if (bytesRead == 0) // odczytano 0 bajtów -> klient się rozłączył
                    {
                        printf("Client disconnected\n");
                        memcpy(&cursor.mtext, &username, strlen(username));
                        msg.mtype = 3;
                        // prześlij nazwę rozłączonego klienta pozostałym klientom, aby usunęły go ze swoich list
                        for (int i = 0; i < map->find((std::string)filename)->second - 1; i++)
                            msgsnd(msgid, &msg, sizeof(msg.mtext), 0);
                        // zakończ odbieranie danych dla tego procesu
                        isConnected = false;
                    }
                    else
                    {
                        perror("recv");
                    }
                    usleep(SLEEPTIME);
                }
                stop = std::chrono::high_resolution_clock::now();
                duration = std::chrono::duration_cast<std::chrono::milliseconds>(stop - start);
                if(duration.count() > 20000)
                {
                    start = std::chrono::high_resolution_clock::now();
                    //synchronizacja
                    printf("Synchronizing!\n");
                    mtx.lock();
                    std::ifstream fin(filename);
                    if (!is_empty(fin))
                    {
                        nlohmann::json j = nlohmann::json::parse(fin);
                        text_arr = j["vector"];
                    }
                    mtx.unlock();
                    fin.close();
                    filled_lines=0;
                    for(int i=0; i<(int)text_arr.size(); i++)
                        if((text_arr[i].compare("")) != 0)
                            filled_lines++;
                    printf("Should send %d lines\n",filled_lines);
                    write(cfd, ("4."+std::to_string(filled_lines)).c_str(), strlen(std::to_string((int)text_arr.size()).c_str())+2);
                    usleep(SLEEPTIME/2);
                    for (int i = 0; i < (int)text_arr.size(); i++)
                    {
                        if((text_arr[i].compare("")) != 0)
                        {
                            write(cfd, text_arr[i].c_str(), strlen(text_arr[i].c_str()));
                            usleep(SLEEPTIME/((int)text_arr.size()*2));
                        }
                    }
                }
            }
            // po tym należy zamknąć wszystko w pamięci i zdekrementować liczbę aktywnych użytkowników
            map->find((std::string)filename)->second--;
            close(cfd);
            // jeżeli to ostatni użytkownik podłączony do danego pliku, zamknij kolejkę komunikatów
            if (map->find((std::string)filename)->second == 0)
            {
                printf("All clients have disconnected from file %s!\n", filename);
                msgctl(msgid, IPC_RMID, nullptr);
            }
            exit(0);
        }
        // przekierowanie ctrl+c do funkcji zajmującej się czyszczeniem danych z pamięci
        signal(SIGINT, sigint_handler);
        close(cfd);
    }
    return 0;
}

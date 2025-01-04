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
#include <fcntl.h>
#include <map>
#include "json.hpp"

struct message
{
    long mtype;
    std::string mtext;
};

bool is_empty(std::ifstream &pFile)
{
    return pFile.peek() == std::ifstream::traits_type::eof();
}

int add_table(const std::string filename, std::vector<std::string> &text_arr)
{
    std::ifstream fin(filename);
    if (!fin)
        return -1; //-1 means there was a problem with file reading
    if (!is_empty(fin))
    {
        nlohmann::json j = nlohmann::json::parse(fin);
        text_arr = j["vector"];
    }
    fin.close();
    return 0;
}

int MAXIMUM = 10;
int limit = 0;
std::map<std::string, int> files;

void childend(int signo)
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

void splitChar(const char *text, char *text1, char *text2)
{
    for (; *text != '\0' && *text != '|';)
        *text1++ = *text++;
    *text1 = '\0';
    for (; *++text != '\0';)
        *text2++ = *text;
    *text2 = '\0';
}

int main()
{
    socklen_t sl;
    int on = 1;
    int rc;
    char buf[256];
    int sfd, cfd;
    struct sockaddr_in saddr, caddr;

    signal(SIGCHLD, childend);

    saddr.sin_family = AF_INET;
    saddr.sin_addr.s_addr = INADDR_ANY;
    saddr.sin_port = htons(1234);
    sfd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    setsockopt(sfd, SOL_SOCKET, SO_REUSEADDR, (char *)&on, sizeof(on));
    bind(sfd, (struct sockaddr *)&saddr, sizeof(saddr));
    listen(sfd, 10);

    while (1)
    {
        sl = sizeof(caddr);
        while (limit >= MAXIMUM)
            sleep(1);
        cfd = accept(sfd, (struct sockaddr *)&caddr, &sl);
        limit++;
        if (!fork())
        {
            close(sfd);
            fcntl(cfd, F_SETFL, O_NONBLOCK);

            char filename[256], username[256], typefilename[256];
            rc = _read(cfd, buf, sizeof(buf));
            splitChar(buf, typefilename, username);
            memmove(filename, typefilename + 1, strlen(typefilename + 1) + 1);
            if (files.find(filename) == files.end())
            {
                files[filename] = 1;
                std::ofstream fout(filename);
                fout.close();
            }
            else
                files[filename]++;

            std::vector<std::string> text_arr;
            if (add_table(filename, text_arr) == -1)
            {
                printf("There was a problem fetching a file data!\n");
            }

            key_t key;
            int msgid;

            // ftok to generate unique key
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

            // mtype: 1 for normal messaging, 0 for answering cursors, 2 at the start for user detection, 3 means a user disconnected
            // todo: make buf have only username and unique identifier to make sure other clients know it's a new user and place him at the end of the first line
            // idea: '1' at the start of the message means that a new edit is being sent, while '2' at the start means a new user has been detected
            // maybe when you're thinking of concurrency and memory safety, wait for '0' messages only a given time, if somebody's cursor times out, then they're outta luck
            message msg;
            msg.mtype = 2;
            msg.mtext = (std::string)buf; // when later process detects a message that starts with 2 and sends it to frontend, it will then take care of putting it at the end of the first line of the file
            while (msgrcv(msgid, &msg, sizeof(msg.mtext), 0, IPC_NOWAIT) != -1)
                ;
            msgsnd(msgid, &msg, sizeof(msg), 0);

            // todo: make the file access itself concurrent and safe, idk, use semaphors or smth
            // for debug purposes
            write(1, buf, rc);
            write(1, "\n", strlen("\n"));

            std::string s = std::to_string(text_arr.size());
            char const *pchar = s.c_str(); // use char const* as target type
            std::cout << pchar << std::endl;
            write(cfd, pchar, strlen(pchar));
            rc = read(cfd, buf, sizeof(buf));
            for (int i = 0; i < (int)text_arr.size(); i++)
            {
                text_arr[i].push_back('\n'); // will later revise to see if it's necessary to do it this way
                write(cfd, text_arr[i].c_str(), strlen(text_arr[i].c_str()));
                // sleep(10);
            }
            // todo: return cursor to the end of the first line
            // todo: wait a given number of time for everyone's cursors
            message cursor;
            int i = 0;
            while (i < files[filename] - 1)
            {
                if (msgrcv(msgid, &cursor, sizeof(cursor), 0, IPC_NOWAIT) != -1)
                {
                    i++;
                    // todo: send these cursors to frontend, maybe '3' would be suitable? Anyway, reading that is frontend's job to tackle
                    write(cfd, ("3" + cursor.mtext).c_str(), strlen(cursor.mtext.c_str()));
                }
                else if (errno != ENOMSG)
                {
                    perror("msgrcv");
                }
            }
            bool isConnected = true;
            while (msgrcv(msgid, &msg, sizeof(msg.mtext), 1, IPC_NOWAIT) != -1)
                ;
            while (msgrcv(msgid, &msg, sizeof(msg.mtext), 2, IPC_NOWAIT) != -1)
                ;
            while (isConnected) // todo: check if there's a better way to check if a user is still connected
            {
                fd_set readFds;
                FD_ZERO(&readFds);
                FD_SET(cfd, &readFds);
                timeval timeout{};
                timeout.tv_sec = 0;
                timeout.tv_usec = 10000; // 10 ms timeout
                // todo: make the program check two things: read() for user input from client and msgrcv() for checking message queue for updates (if any updates, then deliver them to the client)
                if (msgrcv(msgid, &cursor, sizeof(cursor), 1, IPC_NOWAIT) != -1)
                {
                    if (cursor.mtext[0] == '2')
                    {
                        // todo: send these new cursors to frontend, maybe '4' would be suitable? Anyway, that's frontend's job to tackle
                        write(1, ("4" + cursor.mtext).c_str(), strlen(cursor.mtext.c_str()));
                        write(cfd, ("4" + cursor.mtext).c_str(), strlen(cursor.mtext.c_str()));
                    }
                }
                // todo: read cfd to check if frontend sent anything, then send the message to propagate it
                int activity = select(cfd + 1, &readFds, nullptr, nullptr, &timeout);
                if (activity > 0 && FD_ISSET(cfd, &readFds))
                {
                    ssize_t bytesRead = recv(cfd, buf, sizeof(buf) - 1, 0);
                    if (bytesRead > 0)
                    {
                        buf[bytesRead] = '\0';
                        printf("Received from socket: ");
                        printf(buf);
                        printf("\n");
                        // todo: insert and propagate the message
                    }
                    else if (bytesRead == 0)
                    {
                        printf("Client disconnected\n");
                        isConnected = false;
                    }
                    else
                    {
                        perror("recv");
                    }
                }
            }
            // after that happens, close everything, think about keeping a dict or smth for a list of processes that work on the same file, in case you'll have to close something additionally if it's the last process to shut down
            files[filename]--;
            close(cfd);
            if (files[filename] == 0)
            {
                printf("All clients have disconnected!\n");
                msgctl(msgid, IPC_RMID, nullptr);
            }
            exit(0);
        }
        close(cfd);
    }
    return 0;
}
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
#include <map>
#include "json.hpp"

struct message
{
    long mtype;
    std::string mtext;
};

int add_table(const std::string filename, std::vector<std::string> & text_arr)
{
    std::ifstream fin(filename);
    if(!fin)
        return -1; //-1 means there was a problem with file reading
    nlohmann::json j = nlohmann::json::parse(fin);
    text_arr = j["vector"];
    fin.close();
    return 0;
}

int MAXIMUM = 10;
int limit = 0;
std::map<std::string, int> files;

void childend(int signo) { wait(NULL); limit--;}

int _read(int sfd, char *buf, int bufsize) {
    int i, rc = 0;
    do {
        i = read(sfd, buf, bufsize);
        if (i < 0) return i;
        bufsize -= i;
        buf += i;
        rc += i;
    } while (*(buf-1) != '\n');
    return rc;
}

void splitChar(const char *text,  char *text1, char *text2)
{
   for (;*text!='\0' && *text != '|';) *text1++ = *text++;
   *text1 = '\0';
   for (;*++text!='\0';) *text2++ = *text;
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
    setsockopt(sfd, SOL_SOCKET, SO_REUSEADDR, (char*)&on,sizeof(on));
    bind(sfd, (struct sockaddr*)&saddr, sizeof(saddr));
    listen(sfd, 10);

    while(1) {
        sl = sizeof(caddr);
        while(limit >= MAXIMUM)
            sleep(1);
        cfd = accept(sfd, (struct sockaddr*)&caddr, &sl);
        limit++;
        if (!fork()) {
            close(sfd);
            char filename[256], username[256];
            rc = _read(cfd, buf, sizeof(buf));
            splitChar(buf, filename, username);
            if (files.find(filename) == files.end())
            {
                files[filename]=1;
                //todo: create a blank file of a specified name
            }
            else
                files[filename]++;

            key_t key;
            int msgid;

            // ftok to generate unique key
            key = ftok(buf, 65);

            // msgget creates a message queue
            // and returns identifier
            msgid = msgget(key, 0666 | IPC_CREAT);
            
            //todo: make buf have only username and unique identifier to make sure other clients know it's a new user and place him at the end of the first line
            //idea: '1' at the start of the message means that a new edit is being sent, while '2' at the start means a new user has been detected
            //maybe '3' means a user disconnected or smth, idk
            //then maybe '0' is a special answer for a new user intended to get everybody's cursors, when somebody sends '2' to everyone, they then wait
            //for (int)files[filename] messages starting with '0' that are just their cursors' positions
            //maybe when you're thinking of concurrency and memory safety, wait for '0' messages only a given time, if somebody's cursor times out, then they're outta luck
            message msg;
            msg.mtype = 1;
            msg.mtext = "2"+(std::string)buf;
            msgsnd(msgid, &msg, sizeof(msg), 0);

            //for debug purposes
            write(1, buf, rc);
            write(1, "\n", strlen("\n"));

            //todo: make the file access itself concurrent and safe, idk, use semaphors or smth, plus now make buf have filename only
            std::vector<std::string> text_arr;
            nlohmann::json j;
            add_table(buf,text_arr);
            std::string s = std::to_string(text_arr.size());
            char const *pchar = s.c_str();  //use char const* as target type
            std::cout << pchar << std::endl;
            write(cfd, pchar, strlen(pchar));
            rc = read(cfd, buf, sizeof(buf));
            for(int i=0; i<text_arr.size(); i++)
            {
                text_arr[i].push_back('\n'); //will later revise to see if it's necessary to do it this way
                write(cfd, text_arr[i].c_str(), strlen(text_arr[i].c_str()));
                //sleep(10);
            }
            //todo: return cursor to the end of the first line
            //todo: wait a given number of time for everyone's cursors
            //IMPORTANT idea: maybe try to make different message queues for '0' '1' '2' and '3', since these messages are bound to intertwine, hence they're gonna create some errors
            message cursor;
            for(int i=0; i<files[filename]-1; i++)
            {
                msgrcv(msgid, &cursor, sizeof(cursor), 1, 0);
                //todo: send these cursors to frontend, maybe '4' would be suitable? Anyway, that's frontend's job to tackle
            }
            bool isConnected = true;
            while(isConnected) //todo: change infinite loop to while(not user disconnected)
            {
                //todo: make the program check two things: read() for user input from client and msgrcv() for checking message queue for updates (if any updates, then deliver them to the client)
            }
            //after that close everything, think about keeping a dict or smth for a list of processes that work on the same file, in case you'll have to close something additionally if it's the last process to shut down
            files[filename]--;
            close(cfd);
            exit(0);
        }
        close(cfd);
    }
    return 0;
}
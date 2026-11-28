#include <stdio.h>
#include <time.h>
int main(void) {
 struct timespec m,b,w; char id[80]={0};
 FILE *f=fopen("/proc/sys/kernel/random/boot_id","r");
 if(!f || !fgets(id,sizeof(id),f)) return 2;
 fclose(f); for(int i=0;id[i];i++) if(id[i]=='\n') id[i]=0;
 if(clock_gettime(CLOCK_MONOTONIC,&m)||clock_gettime(CLOCK_BOOTTIME,&b)||clock_gettime(CLOCK_REALTIME,&w)) return 3;
 printf("{\"mono\":%.9f,\"boot\":%.9f,\"wall\":%.9f,\"boot_id\":\"%s\"}\n",
  m.tv_sec+m.tv_nsec/1e9,b.tv_sec+b.tv_nsec/1e9,w.tv_sec+w.tv_nsec/1e9,id);
 return 0;
}

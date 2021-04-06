#define _GNU_SOURCE
#include <sys/sysinfo.h>
#include <dlfcn.h>
#include <stdio.h>

// Copied from https://github.com/justin2004/mssql_server_tiny/blob/7ca5bc1eb3a302d43030c45206bf3d64da34b1d1/wrapper.c

int sysinfo(struct sysinfo *info){
    // clear it
    //dlerror();
    void *pt=NULL;
    typedef int (*real_sysinfo)(struct sysinfo *info);

    // we need the real sysinfo function address
    pt = dlsym(RTLD_NEXT,"sysinfo");
    //printf("pt: %x\n", *(char *)pt);

    // call the real sysinfo system call
    int real_return_val=((real_sysinfo)pt)(info);

    // but then modify its returned totalram field if necessary
    // because sqlserver needs to believe it has "2000 megabytes"
    // physical memory
    if( info->totalram < 1000l * 1000l * 1000l * 2l){ // 2000 megabytes
        info->totalram = 1000l * 1000l * 1000l * 2l ;
    }

    return real_return_val;
}

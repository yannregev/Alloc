This is an implementation of the C functions malloc, calloc and realloc.
It uses a singely linked list to keep track of the chunks of memory that were assigned to the heap by the sbrk system call.
This can also be used as a system malloc by preloading the generated library before executing a code.

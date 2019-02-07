#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <stddef.h>


//Constants
#define TRUE 1
#define FALSE 0
#define MIN_UNMAP_SIZE 1024
#define BATCH_SIZE ALLOC_SIZE * 124
#define ALLOC_SIZE sizeof(long)

//Macros
#define ALIGN_SIZE(size) ((size + (ALLOC_SIZE - 1)) & ~ (ALLOC_SIZE - 1))
#define OVER_HEAD (sizeof(uint32_t) * 2)
#define GET_SIZE(ptr) (*(size_t *)(ptr - 8))
#define GET_NEXT(ptr) (ptr + GET_SIZE(ptr))

void *split(void *ptr, size_t size);
void merge();
void shrink_heap();
void myfree(void *);

void *head = NULL;
void *empty = NULL;
/*
* This function will split a block in two based on size, it return the address of the block
* And will store the other segmant in the free blocks list
*/
void *split(void *ptr, size_t size) {
	if (GET_SIZE(ptr) - size < OVER_HEAD + sizeof(uintptr_t) ) {
	 	return ptr;
	}
	void *free_block = (ptr + size);
	GET_SIZE(free_block) = GET_SIZE(ptr) - size;

	GET_SIZE(ptr) = GET_SIZE(ptr) - GET_SIZE(free_block);
	*(uintptr_t *)free_block = (uintptr_t)head;
	head = free_block;
	return ptr;
}

/*
* This function will merge two neighbouring free blocks
*/
void merge() {
	void *ptr = head;
	while (ptr) {
		void *prev = NULL;
		void *tmp = head;
		while (tmp && !((ptr + GET_SIZE(ptr)) == tmp)) {
				prev = tmp;
				tmp = (void *)*(uintptr_t *)tmp;
		}
		if (tmp) {
			GET_SIZE(ptr) += GET_SIZE(tmp);
			if (!prev) {
				head = (void *)*(uintptr_t *)tmp;
			} else {
				*(uintptr_t *)prev = *(uintptr_t *)tmp;
			}
		}
		ptr = (void *)*(uintptr_t *)ptr;
	}
}

/*
*   This function will find the block with the highest address and if its 
*   size is bigger than MIN_UNMAP_SIZE, its will free it from the heap
*/
void shrink_heap() {
	void *prev = NULL;
	void *ptr = head;
	void *top = sbrk(0);
		while (ptr && !(GET_SIZE(ptr) >= MIN_UNMAP_SIZE && GET_NEXT(ptr) - OVER_HEAD == top)) {				
			prev = ptr;
			ptr = (void *)*( uintptr_t *)ptr;
		}
		if (!ptr) return;
		
		if (!prev) {
			head = (void *)*(uintptr_t *)head;
		} else {
			*(uintptr_t *)prev = *(uintptr_t *)ptr;
		}
		if (brk((ptr - OVER_HEAD)) == -1) perror("brk");
}

/*
*	This function will run through the list of free blocks to find a block with enough size 
*/
void *find_free_block(size_t size) {
	if (!head) return NULL;
	void *ptr = head;
	void *prev = NULL;
	while (ptr && !(GET_SIZE((ptr)) >= size)) {
		prev = ptr;
		ptr = (void *)*( uintptr_t *)ptr;
	}

	if (!ptr) return NULL;

	if (!prev) {
		head = (void *)*(uintptr_t *)head;
	} else {
		*(uintptr_t *)prev = *(uintptr_t *)ptr;
	}
		
	ptr = split(ptr, size);	
	return ptr;
}
/*
*	This function will request more size from the heap with sbrk with MIN(BATCH_SIZE, size)
*/
void *req_inc_size(size_t size) {
	void *ptr;	
	
	if (size < BATCH_SIZE) {
		ptr = sbrk(BATCH_SIZE);	
		ptr = (ptr + OVER_HEAD);
		GET_SIZE(ptr) = BATCH_SIZE;
		return split(ptr, size);
		
	}

	ptr = sbrk(size);	
	ptr = (ptr + OVER_HEAD);
	GET_SIZE(ptr) = size;
	return ptr;
}

void *mymalloc(size_t size)
{
	void *ptr = NULL;
	if (size <= 0) return &empty;
	size = ALIGN_SIZE(size) + OVER_HEAD;
	if (!head) {
 		ptr = req_inc_size(size);
	} else {
		ptr = find_free_block(size);
		if (!ptr) ptr = req_inc_size(size);
	}
	return ptr;
}

void *mycalloc(size_t nmemb, size_t size)
{
    void *ptr = mymalloc(nmemb * size);
    if (!ptr) return NULL;
    
    bzero(ptr, ALIGN_SIZE(nmemb * size));
    
    return ptr;
}

void myfree(void *ptr)
{
	if (!ptr) return;
	if (ptr == &empty) {
		ptr = NULL;
		return;
	}

	*(uintptr_t *)ptr = (uintptr_t)head;
	head = ptr;
	merge();
	shrink_heap();
}

void *myrealloc(void *ptr, size_t size)
{
	if (!ptr) return mymalloc(size);
    size = ALIGN_SIZE(size) + OVER_HEAD;
    if (size <= GET_SIZE(ptr)) return ptr;
    if (size < GET_SIZE(ptr)) return split(ptr, size);
    void *tmp;
    tmp = mymalloc(size);
    if (!tmp) return NULL;
    memcpy(tmp, ptr, GET_SIZE(ptr));
    myfree(ptr);
    return tmp;
}


/*
 * Enable the code below to enable system allocator support for your allocator.
 */
#if 1
void *malloc(size_t size) { return mymalloc(size); }
void *calloc(size_t nmemb, size_t size) { return mycalloc(nmemb, size); }
void *realloc(void *ptr, size_t size) { return myrealloc(ptr, size); }
void free(void *ptr) { myfree(ptr); }
#endif

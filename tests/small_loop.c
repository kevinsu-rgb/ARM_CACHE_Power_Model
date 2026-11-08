#include <stdio.h>

#define ARRAY_SIZE (1 << 16)
#define PASSES 20

int main(void) {
    volatile unsigned long long sum = 0;
    unsigned int data[ARRAY_SIZE];

    for (int i = 0; i < ARRAY_SIZE; ++i) {
        data[i] = i + 1;
    }

    for (int p = 0; p < PASSES; ++p) {
        for (int i = 0; i < ARRAY_SIZE; ++i) {
            sum += data[i] * (p + 1);
        }
    }

    printf("Result: %llu\n", sum);
    return 0;
}

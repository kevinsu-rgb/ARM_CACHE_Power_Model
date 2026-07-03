#include <stdio.h>

int main() {
    int result = 0;
    for (int i = 0; i < 1000; i++) {
        result += i;
    }
    printf("Result: %d\n", result);
    return 0;
}

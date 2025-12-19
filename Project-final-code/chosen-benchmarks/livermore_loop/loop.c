#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <time.h>

/*
 * Standalone "Livermore_loop" 
 *
 * Usage:
 *   ./livermore_big N ITER
 *
 * If not provided:
 *   N    defaults to 100000
 *   ITER defaults to 200
 *
 * Runtime ~ proportional to N * ITER.
 */

static void die(const char *msg) {
    fprintf(stderr, "%s\n", msg);
    exit(1);
}

int main(int argc, char **argv) {
    // ---- configuration ----
    long N    = (argc > 1) ? atol(argv[1]) : 100000;  // vector length
    long ITER = (argc > 2) ? atol(argv[2]) : 10000;     // outer iterations

    if (N <= 10)     N    = 10;
    if (ITER <= 0)   ITER = 1;

    printf("Livermore-big: N = %ld, ITER = %ld\n", N, ITER);

    // ---- allocate big 1D vectors on the heap ----
    double *X  = (double*)malloc(sizeof(double)* (N+16));
    double *Y  = (double*)malloc(sizeof(double)* (N+16));
    double *Z  = (double*)malloc(sizeof(double)* (N+16));
    double *U  = (double*)malloc(sizeof(double)* (N+16));
    double *V  = (double*)malloc(sizeof(double)* (N+16));
    double *W  = (double*)malloc(sizeof(double)* (N+16));
    double *G  = (double*)malloc(sizeof(double)* (N+16));
    double *Bv = (double*)malloc(sizeof(double)* (N+16)); // for recurrence
    double *Tmp= (double*)malloc(sizeof(double)* (N+16));

    if (!X || !Y || !Z || !U || !V || !W || !G || !Bv || !Tmp)
        die("malloc failed");

    // Small matrices for matrix-matrix kernel
    const int MM = 32;
    double A[MM][MM];
    double B[MM][MM];
    double C[MM][MM];

    // ---- initialize data ----
    for (long i = 0; i < N+16; ++i) {
        X[i]  = 1.0;
        Y[i]  = 2.0 + 0.000001 * i;
        Z[i]  = 3.0 - 0.000001 * i;
        U[i]  = 0.5 * (i % 100);
        V[i]  = 0.25 * (i % 50);
        W[i]  = 0.1 * (i % 20);
        G[i]  = 1.0 + 0.0001 * (i % 37);
        Bv[i] = 0.5 / (1.0 + (i % 5));
        Tmp[i]= 0.0;
    }

    for (int i = 0; i < MM; ++i) {
        for (int j = 0; j < MM; ++j) {
            A[i][j] = (i + j + 1) * 0.001;
            B[i][j] = (i == j) ? 1.0 : 0.5 * 0.001 * (i + j);
            C[i][j] = 0.0;
        }
    }

    // constants reminiscent of original kernels
    double Q = 0.5, R = 1.1, T = 0.9;
    double dk = 0.01, S = 0.1;

    double checksum = 0.0;
    clock_t t0 = clock();

    // ---- main outer loop ----
    for (long iter = 0; iter < ITER; ++iter) {

        // ---------------- Kernel 1: hydro-like fragment ----------------
        // X[i] = Q + Y[i]*(R*Z[i+1] + T*Z[i+2])
        for (long i = 0; i < N; ++i) {
            long ip1 = (i + 1) % N;
            long ip2 = (i + 2) % N;
            X[i] = Q + Y[i] * (R * Z[ip1] + T * Z[ip2]);
        }

        // ---------------- Kernel 2: ICCG-like recurrence ---------------
        // simple triangular recurrence:
        // W[i] = W[i] - V[i]*W[i-1] - V[i+1]*W[i+1]
        // (with clamped boundaries)
        for (long i = 1; i < N-1; ++i) {
            W[i] = W[i] - V[i] * W[i-1] - V[i+1] * W[i+1];
        }

        // ---------------- Kernel 3: inner product ----------------------
        double q = 0.0;
        for (long i = 0; i < N; ++i) {
            q += Z[i] * X[i];
        }
        checksum += q * 1e-12; // accumulate tiny amount to avoid overflow

        // ---------------- Kernel 4: banded-like update -----------------
        // X[i] -= Y[i-3]*Z[i] + Y[i]*Z[i+2]
        for (long i = 3; i < N-2; ++i) {
            X[i] -= Y[i-3]*Z[i] + Y[i]*Z[i+2];
        }

        // ---------------- Kernel 5: tri-diagonal elimination ----------
        // X[i] = Z[i]*(Y[i] - X[i-1])
        for (long i = 1; i < N; ++i) {
            X[i] = Z[i] * (Y[i] - X[i-1]);
        }

        // ---------------- Kernel 6: general recurrence -----------------
        // simple 2-term recurrence:
        // W[i] += Bv[i] * W[i-1] + 0.5*Bv[i]*W[i-2]
        for (long i = 2; i < N; ++i) {
            W[i] += Bv[i] * W[i-1] + 0.5 * Bv[i] * W[i-2];
        }

        // ---------------- Kernel 7: equation-of-state-like -------------
        // U[i] = U[i] + R*(Z[i] + R*Y[i])
        // plus some extra chaining similar in spirit
        for (long i = 0; i < N-6; ++i) {
            double u0 = U[i];
            U[i] = u0 + R*( Z[i] + R*Y[i] )
                     + T*( U[i+3] + R*(U[i+2] + R*U[i+1]) );
        }

        // ---------------- Kernel 8: prefix sum -------------------------
        // X is prefix sum of Y
        if (N > 0) {
            X[0] = Y[0];
            for (long i = 1; i < N; ++i) {
                X[i] = X[i-1] + Y[i];
            }
        }

        // ---------------- Kernel 9: first difference -------------------
        // Z[i] = Y[i+1] - Y[i]
        for (long i = 0; i < N-1; ++i) {
            Z[i] = Y[i+1] - Y[i];
        }
        Z[N-1] = Z[N-2];

        // ---------------- Kernel 10: transport-like update ------------
        // discrete form: X[i] = (W[i] + V[i]*dn)*X[i] + U[i];
        // dn depends on difference Y[i] - G[i]/(X[i]+dk)
        for (long i = 0; i < N; ++i) {
            double di = Y[i] - G[i] / (X[i] + dk);
            double dn = 0.2;
            if (di != 0.0) {
                dn = Z[i] / di;
                if (dn > 1.0) dn = 1.0;
                if (dn < 0.0) dn = 0.0;
            }
            X[i] = ((W[i] + V[i]*dn) * X[i] + U[i]) / (1.0 + V[i]*dn);
        }

        // ---------------- Kernel 11: Planck-like distribution ---------
        // W[i] = X[i] / (exp(U[i]) - 1)
        for (long i = 0; i < N; ++i) {
            double e = exp(U[i]);
            if (e > 1.0)
                W[i] = X[i] / (e - 1.0);
        }

        // ---------------- Kernel 12: small matrix-matrix multiply -----
        // C = C + A * B
        for (int i = 0; i < MM; ++i) {
            for (int j = 0; j < MM; ++j) {
                double sum = C[i][j];
                for (int k = 0; k < MM; ++k) {
                    sum += A[i][k] * B[k][j];
                }
                C[i][j] = sum;
            }
        }

        // Simple “work sink” to keep compiler from removing loops
        if ((iter & 31) == 0) {
            checksum += X[N/2] * 1e-9 + W[N/3] * 1e-9;
            printf("Iter %ld / %ld, partial checksum = %.6e\n",
                   iter, ITER, checksum);
        }
    }

    clock_t t1 = clock();
    double elapsed = (double)(t1 - t0) / CLOCKS_PER_SEC;

    // Final checksum
    for (long i = 0; i < N; ++i) {
        checksum += X[i]*1e-16 + W[i]*1e-16 + U[i]*1e-16;
    }
    printf("Final checksum = %.12e\n", checksum);
    printf("Elapsed (host wall time) = %.3f seconds\n", elapsed);

    free(X); free(Y); free(Z); free(U); free(V);
    free(W); free(G); free(Bv); free(Tmp);

    return 0;
}

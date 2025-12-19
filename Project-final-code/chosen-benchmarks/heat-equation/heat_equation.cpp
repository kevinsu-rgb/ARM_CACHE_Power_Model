#include <iostream>
#include <vector>
#include <cmath>
#include <cstdlib>

int main(int argc, char *argv[])
{
    if (argc < 4) {
        std::cerr << "Usage: " << argv[0]
                  << " NX NY STEPS [alpha=0.1] [dx=1.0] [dy=1.0]\n";
        return 1;
    }

    int NX    = std::atoi(argv[1]);
    int NY    = std::atoi(argv[2]);
    int STEPS = std::atoi(argv[3]);

    double alpha = (argc > 4) ? std::atof(argv[4]) : 0.1;
    double dx    = (argc > 5) ? std::atof(argv[5]) : 1.0;
    double dy    = (argc > 6) ? std::atof(argv[6]) : 1.0;

    // Simple stability check (not strict, just a warning)
    double dt = 0.1;
    double cfl = alpha * dt * (1.0/(dx*dx) + 1.0/(dy*dy));
    if (cfl >= 0.5) {
        std::cerr << "Warning: CFL condition may be violated (cfl=" << cfl
                  << "). Simulation might be unstable.\n";
    }

    int N = NX * NY;
    std::vector<double> u(N, 0.0);
    std::vector<double> u_new(N, 0.0);

    // Initial condition: hot square in the middle
    for (int i = NX/4; i < 3*NX/4; i++) {
        for (int j = NY/4; j < 3*NY/4; j++) {
            u[i * NY + j] = 100.0;
        }
    }

    // Time stepping
    for (int step = 0; step < STEPS; step++) {

        // simple Dirichlet boundary: borders fixed at 0
        for (int i = 1; i < NX - 1; i++) {
            for (int j = 1; j < NY - 1; j++) {

                int idx = i * NY + j;

                double u_center = u[idx];
                double u_up      = u[(i-1)*NY + j];
                double u_down    = u[(i+1)*NY + j];
                double u_left    = u[i*NY + (j-1)];
                double u_right   = u[i*NY + (j+1)];

                double dudx2 = (u_left - 2.0*u_center + u_right) / (dx*dx);
                double dudy2 = (u_up   - 2.0*u_center + u_down)  / (dy*dy);

                u_new[idx] = u_center + alpha * dt * (dudx2 + dudy2);
            }
        }

        // swap buffers
        u.swap(u_new);

        // occasional progress print (cheap, but you can remove for gem5)
        if (STEPS > 0 && step % (STEPS/10 + 1) == 0) {
            std::cout << "Step " << step << " / " << STEPS << " done\n";
        }
    }

    // Output one value to avoid being optimized away
    int cx = NX / 2;
    int cy = NY / 2;
    std::cout << "Final center temperature at (" << cx << "," << cy << "): "
              << u[cx * NY + cy] << std::endl;

    return 0;
}

# ARM_Power_Model
This repo contains a power and thermal model of a ARM CPU.
# Cache Hierarchy Block Diagram
![Alt text](/images/Cache_Hierarchy.png)

# Instructions (Assuming Project is Cloned in Home directory (~))
1. Make sure you have built ARM execeutable gem5.opt in gem5/build/ARM/gem5.opt (or just have ARM gem5.opt)
2. Code for cache and power model are in ~/ARM_Power_Model/Power_src
3. To run code: "Path to ARM gem5.opt" main.py
EX: ~/ARM_Power_Model/gem5/build/ARM/gem5.opt main.py

Flags
--binary (points to benchmark/executable, default: program_arm64)

--l1i_size (L1 Instruction Cache size, default: 32KiB)

--l1d_size (L1 Data Cache size, default: 32KiB)

--l2_size (L2 Cache size, default: 256KiB)

--l3_size (L3 Cache size, default: 2MiB)

--l1i_assoc (L1 Instruction Cache Associciation, default: 8)

--l1d_assoc (L1 Data Cache Associciation, default: 8)

--l2_assoc (L2 Cache Associciation, default: 16)

--l3_assoc (L3 Cache Associciation, default: 32)

--block_size (Cannot change, default to 64 bytes)

--l1i_replacement_policy
--l1d_replacement_policy
--l2_replacement_policy
--l3_replacement_policy
* All cache policies default to Least Recentl Used (LRURP)
* All options are: LRURP, FIFORP, and TreePLRURP

--cpu_type (Options: TIMING, ATOMIC, KVM, default: TIMING)

# Running benchmarks example 
# HPCCG 
/path/to/gem5/build/ARM/gem5.opt \
  /path/to/gem5/configs/example/se.py \
  -c /home/bohan/gem5-bench/hpccg/hpccg.elf \
  --options="128 128 128" \
  --cwd=/home/bohan/gem5-bench/hpccg \
  --caches --l2cache


# heat_equation 

/path/to/gem5/build/ARM/gem5.opt \
  /path/to/gem5/configs/example/se.py \
  -c /path/to/heat2d.elf \
  --options="256 256 200" \
  --caches --l2cache
    --caches --l2cache

# blacksholes 

/path/to/gem5/build/ARM/gem5.opt \
  /path/to/gem5/configs/example/se.py \
  -c /home/bohan/gem5-bench/blackscholes/blackscholes.elf \
  --options="bs_input.txt bs_output.txt" \
    --caches --l2cache

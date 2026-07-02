%% AdapVPP main simulation script.

this_file = mfilename('fullpath');
if isempty(this_file)
    project_root = pwd;
else
    project_root = fileparts(fileparts(this_file));
end

cd(project_root);
addpath(genpath(fullfile(project_root, 'matlab')));

cfg = vpp_config();
rng(cfg.random_seed);

data_path = fullfile(project_root, 'data', 'processed', 'matlab', 'vpp_typical_day.mat');
if exist(data_path, 'file') ~= 2
    error('Missing data file: %s. Run scripts/preprocess_vpp_data.py first.', data_path);
end

data = load(data_path);
P_solar = data.P_solar;
P_wind = data.P_wind;
P_load = data.P_load;

hour_idx = 12;
P_solar_now = P_solar(hour_idx, :).';
P_wind_now = P_wind(hour_idx, :).';
P_load_now = P_load(hour_idx);

P_renewable_total = sum(P_solar_now) + sum(P_wind_now);
P_bess_ref = P_load_now - P_renewable_total;
P_demand = P_load_now;

fprintf('=== Simulation hour: typical day hour %d ===\n', hour_idx);
fprintf('Solar total output: %.2f MW\n', sum(P_solar_now));
fprintf('Wind total output: %.2f MW\n', sum(P_wind_now));
fprintf('Load demand: %.2f MW\n', P_demand);
fprintf('BESS reference output: %.2f MW\n', P_bess_ref);

fprintf('\n--- Scenario 1: Standard ADMM, ideal communication ---\n');
results.scenario1 = run_scenario1_ideal(P_demand, cfg);
fprintf('Iterations: %d, total cost: %.4f\n', results.scenario1.iter, results.scenario1.total_cost);

fprintf('\n--- Scenario 2: ET-ADMM, light weak communication ---\n');
results.scenario2 = run_scenario2_light(P_demand, cfg);
fprintf('Iterations: %d, communication count: %d, saving: %.1f%%\n', ...
    results.scenario2.iter, results.scenario2.comm, results.scenario2.comm_saving);

fprintf('\n--- Scenario 2b: Standard ADMM, light weak communication ---\n');
results.scenario2b = run_scenario2b_standard_weak(P_demand, cfg);
fprintf('Iterations: %d, diverged: %d, communication saving: %.1f%%\n', ...
    results.scenario2b.iter, results.scenario2b.diverged, results.scenario2b.comm_saving);

fprintf('\n--- Scenario 3: ET-ADMM, heavy weak communication ---\n');
results.scenario3 = run_scenario3_heavy(P_demand, cfg);
fprintf('Iterations: %d, communication count: %d, saving: %.1f%%\n', ...
    results.scenario3.iter, results.scenario3.comm, results.scenario3.comm_saving);

fprintf('\n--- Scenario 3b: Standard ADMM, heavy weak communication ---\n');
results.scenario3b = run_scenario3b_standard_weak(P_demand, cfg);
fprintf('Iterations: %d, diverged: %d, communication saving: %.1f%%\n', ...
    results.scenario3b.iter, results.scenario3b.diverged, results.scenario3b.comm_saving);

fprintf('\n--- Scenario 4: ET-ADMM, outage and recovery ---\n');
results.scenario4 = run_scenario4_recovery(P_demand, cfg);
fprintf('Iterations: %d, communication count: %d, saving: %.1f%%\n', ...
    results.scenario4.iter, results.scenario4.comm, results.scenario4.comm_saving);

[summary_table, weak_comparison_table] = compare_all_scenarios(results);

cost_gap_table = cost_gap_analysis(results, cfg);

fprintf('\n--- Monte Carlo validation: 30 runs per weak communication condition ---\n');
mc_summary_table = monte_carlo_test(30, P_demand, cfg);

results_dir = fullfile(project_root, 'matlab', 'results');
if ~exist(results_dir, 'dir')
    mkdir(results_dir);
end

save(fullfile(results_dir, 'simulation_results.mat'), ...
    'results', 'summary_table', 'weak_comparison_table', 'cost_gap_table', 'mc_summary_table', ...
    'cfg', 'P_demand', 'P_solar_now', 'P_wind_now', 'P_load_now');
fprintf('\nResults saved to matlab/results/simulation_results.mat\n');

plot_results(results, cfg, P_demand);

function saving = communication_saving(comm_count, iter_count)
% Communication saving percentage relative to full broadcasting by 5 nodes.

baseline = max(iter_count * 5, 1);
saving = max(0, min(100, (1 - comm_count / baseline) * 100));

end

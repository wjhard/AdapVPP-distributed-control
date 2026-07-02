function msg_received = communication_model(msg_sent, buffer, k, delay_steps, loss_rate, break_start, break_end)
% Communication channel model with delay, packet loss, and outage.

if nargin < 6 || isempty(break_start)
    break_start = inf;
end
if nargin < 7 || isempty(break_end)
    break_end = inf;
end

if k >= break_start && k <= break_end
    safe_step = max(1, break_start - 1);
    if safe_step <= numel(buffer) && ~isempty(buffer{safe_step})
        msg_received = buffer{safe_step};
    else
        msg_received = msg_sent;
    end
    return;
end

receive_from_step = k - delay_steps;
if receive_from_step < 1
    receive_from_step = 1;
end

if receive_from_step <= numel(buffer) && ~isempty(buffer{receive_from_step})
    msg_received = buffer{receive_from_step};
else
    msg_received = msg_sent;
end

for i = 1:numel(msg_received)
    if rand() < loss_rate
        hold_step = max(1, receive_from_step - 1);
        if hold_step <= numel(buffer) && ~isempty(buffer{hold_step})
            msg_received(i) = buffer{hold_step}(i);
        end
    end
end

end

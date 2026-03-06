function opts = optimoptions(solver, varargin)
% OPTIMOPTIONS  Shim replacing Optimization Toolbox optimoptions.
%
% Returns a simple struct with the name-value pairs so fsolve shim can
% read them.  Accepts any solver name string as the first argument.

    opts = struct();
    opts.Solver = solver;

    % Parse name-value pairs
    for k = 1:2:numel(varargin)
        name = varargin{k};
        val  = varargin{k+1};
        opts.(name) = val;
    end

    % Map legacy names to modern names so the fsolve shim finds them
    if isfield(opts, 'TolFun') && ~isfield(opts, 'FunctionTolerance')
        opts.FunctionTolerance = opts.TolFun;
    end
    if isfield(opts, 'TolX') && ~isfield(opts, 'StepTolerance')
        opts.StepTolerance = opts.TolX;
    end
    if isfield(opts, 'MaxIter') && ~isfield(opts, 'MaxIterations')
        opts.MaxIterations = opts.MaxIter;
    end
    if isfield(opts, 'MaxFunEvals') && ~isfield(opts, 'MaxFunctionEvaluations')
        opts.MaxFunctionEvaluations = opts.MaxFunEvals;
    end
end

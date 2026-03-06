function MAGEC_CSV_Wrapper(input_csv, output_csv, settings)
% MAGEC_CSV_Wrapper  CSV I/O wrapper for MAGEC_Solver_v1b.p
%
%   MAGEC_CSV_Wrapper(INPUT_CSV, OUTPUT_CSV, SETTINGS)
%
%   Reads a CSV input file, converts it to a temporary xlsx for the
%   MAGEC solver, runs the solver with the given settings struct,
%   then converts the xlsx output back to CSV.  This avoids the slow
%   xlsx I/O on the Python side (openpyxl) while keeping the original
%   compiled solver unchanged.
%
%   INPUT_CSV and OUTPUT_CSV should be basenames (not full paths).
%   The working directory (pwd) must contain INPUT_CSV.
%
%   Bundled with volcatenate.

    % Read CSV input from pwd
    T_in = readtable(fullfile(pwd, input_csv), 'TextType', 'string', ...
                     'PreserveVariableNames', true);

    % Use simple basenames for temp files (solver expects pwd-relative)
    uid = char(java.util.UUID.randomUUID);
    tmp_in_name  = ['_vcn_' uid '.xlsx'];
    tmp_out_name = ['_vcn_' uid '_out.xlsx'];

    % Write temporary xlsx with 'input' sheet (MAGEC's expected format)
    writetable(T_in, fullfile(pwd, tmp_in_name), 'Sheet', 'input');

    % Clean up function to remove temp files on exit (even on error)
    cleanup = onCleanup(@() delete_if_exists( ...
        fullfile(pwd, tmp_in_name), fullfile(pwd, tmp_out_name)));

    % Call the original compiled solver with BASENAMES
    % (solver uses fullfile(pwd, filename) internally)
    MAGEC_Solver_v1b(tmp_in_name, tmp_out_name, settings);

    % Read solver output xlsx and write as CSV
    tmp_out_path = fullfile(pwd, tmp_out_name);
    if exist(tmp_out_path, 'file')
        T_out = readtable(tmp_out_path, 'Sheet', 'output', ...
                          'TextType', 'string', ...
                          'PreserveVariableNames', true);
        writetable(T_out, fullfile(pwd, output_csv));
    else
        warning('MAGEC_CSV_Wrapper:NoOutput', ...
                'MAGEC solver produced no output file.');
    end
end

function delete_if_exists(varargin)
    for k = 1:nargin
        if exist(varargin{k}, 'file')
            delete(varargin{k});
        end
    end
end

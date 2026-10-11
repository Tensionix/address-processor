using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace AudionAddressProcessor.Core;

/// <summary>What a short call of the console command answered.</summary>
public sealed record Reply(int Code, string Out, string Err)
{
    public bool Ok => Code == 0;
}

/// <summary>A service line of a run ("::address::{...}"): where the journal is written, how far the work is, the live line, how it ended.</summary>
public sealed class DoorEvent
{
    /// <summary>started, progress, live or finished.</summary>
    public string Kind { get; init; } = "";
    public string Log { get; init; } = "";
    public string ReportDir { get; init; } = "";
    /// <summary>The share of the work done, 0..1; -1 when the line says nothing of it.</summary>
    public double Progress { get; init; } = -1;
    /// <summary>The bar rewritten in place (a stage of the alignment), as one line.</summary>
    public string Live { get; init; } = "";
    /// <summary>done, failed or stopped.</summary>
    public string Outcome { get; init; } = "";
    public string Message { get; init; } = "";
}

/// <summary>The result of a run, as the console command wrote it into its --result file.</summary>
public sealed class RunResult
{
    public string Outcome { get; set; } = "";
    public bool Ok { get; set; }
    public string Message { get; set; } = "";
    public string Source { get; set; } = "";
    public string Log { get; set; } = "";
    public string ReportDir { get; set; } = "";
    public JsonElement Data { get; set; }

    static List<string> Strings(JsonElement value)
    {
        var list = new List<string>();
        switch (value.ValueKind)
        {
            case JsonValueKind.String:
                if (!string.IsNullOrWhiteSpace(value.GetString())) list.Add(value.GetString()!.Trim());
                break;
            case JsonValueKind.Array:
                foreach (var item in value.EnumerateArray()) list.AddRange(Strings(item));
                break;
            case JsonValueKind.Object:
                foreach (var property in value.EnumerateObject()) list.AddRange(Strings(property.Value));
                break;
        }
        return list;
    }

    JsonElement Member(string name) =>
        Data.ValueKind == JsonValueKind.Object && Data.TryGetProperty(name, out var value) ? value : default;

    /// <summary>What the operation made, by kind: "outputs", "reports", "staging", "inputs" (the `artifacts` of its answer), without repeats.</summary>
    public List<string> Artifacts(string kind)
    {
        var found = new List<string>();
        if (Member("artifacts") is { ValueKind: JsonValueKind.Object } artifacts && artifacts.TryGetProperty(kind, out var list)) found.AddRange(Strings(list));
        return found.Distinct(StringComparer.OrdinalIgnoreCase).ToList();
    }

    /// <summary>The files an operation named as its result, in the answer it gave: the artifacts, or what an older operation calls output, outputs or zip.</summary>
    public List<string> Outputs()
    {
        var found = Artifacts("outputs");
        if (found.Count > 0) return found;
        foreach (var name in new[] { "outputs", "output", "zip" }) found.AddRange(Strings(Member(name)));
        return found.Distinct(StringComparer.OrdinalIgnoreCase).ToList();
    }

    /// <summary>The report of the operation as a file, when it named one; "" otherwise.</summary>
    public string ReportFile()
    {
        var reports = Artifacts("reports");
        if (reports.Count > 0) return reports[0];
        return Strings(Member("report")).FirstOrDefault() ?? "";
    }

}

/// <summary>
/// The console command of the engine. A button of the window does nothing a console cannot: it runs
/// address_cli.cmd with the words a person would type, and that line is written into the journal.
/// The window starts the Python of the project directly, with the very environment the wrapper
/// sets - so a path is quoted once, by the system, and not a second time by the rules of cmd.
/// Nothing about addresses is decided here: which fields an operation has, what their defaults
/// are, which of them go to the engine - the command alone knows (system_core\cli.py).
/// </summary>
public static class Door
{
    public const string Control = "::address::";
    public const int ExitDone = 0, ExitFailed = 1, ExitUsage = 2, ExitStopped = 130;

    /// <summary>The command can be called: the wrapper is there and so is the Python of the project.</summary>
    public static bool Ready => File.Exists(Paths.Door) && Paths.Python.Length > 0;

    /// <summary>Why the command cannot be called, in the words of the window; "" when it can.</summary>
    public static string Trouble =>
        !File.Exists(Paths.Door) ? Lang.F("нет файла: {0}", Paths.Door)
        : Paths.Python.Length == 0 ? Lang.F("нет Python проекта ({0}): сначала соберите окружение - builder_main.cmd", Path.Combine(Paths.Root, @"runtime\python.exe"))
        : "";

    // What address_cli.cmd does before it calls Python, repeated word for word: the command is started as a file.
    static string Script => Path.Combine(Paths.Root, "system_core", "cli.py");
    static Dictionary<string, string> Env => new() { ["PYTHONUTF8"] = "1", ["PYTHONIOENCODING"] = "utf-8" };

    static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
    };

    // ------------------------------------------------------------ the files of a run

    public static string ParamsFile => Path.Combine(Paths.Session, "params.json");
    public static string ResultFile => Path.Combine(Paths.Session, "result.json");
    /// <summary>The stop signal: the file appears - the operation stops itself.</summary>
    public static string StopFile => Path.Combine(Paths.Session, "stop.flag");
    /// <summary>Where the engine notes the Excel and Word it started, so that they can be closed if the operation is ended from here.</summary>
    public static string OfficeNotes => Path.Combine(Paths.Session, "office");

    // ------------------------------------------------------------ the lines

    /// <summary>The same call as a console would type it: written into the journal at every start.</summary>
    public static string ConsoleLine(IEnumerable<string> args) =>
        string.Join(" ", new[] { Paths.DoorName }.Concat(args.Select(Quote)));

    static string Quote(string value)
    {
        if (value.Length > 0 && value.IndexOfAny(new[] { ' ', '\t', '"', '&', '(', ')', '^', '=', ';', ',', '%', '|', '<', '>' }) < 0) return value;
        // The rules of the console: a backslash before a quote is doubled, one at the end too, or it would swallow the closing quote.
        var text = new System.Text.StringBuilder("\"");
        int slashes = 0;
        foreach (var c in value)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { text.Append('\\', slashes * 2 + 1).Append('"'); slashes = 0; continue; }
            text.Append('\\', slashes).Append(c);
            slashes = 0;
        }
        text.Append('\\', slashes * 2).Append('"');
        return text.ToString();
    }

    /// <summary>The arguments of a run. The values of the fields go by a file: a text with quotes or line breaks is not for a command line.</summary>
    public static List<string> RunArgs(string operation, string source, string target)
    {
        var args = new List<string> { "run", "--operation", operation };
        if (source.Length > 0) { args.Add("--source"); args.Add(source); }
        if (target.Length > 0) { args.Add("--target"); args.Add(target); }
        args.AddRange(new[] { "--params", ParamsFile, "--result", ResultFile, "--cancel-file", StopFile, "--session-dir", OfficeNotes });
        return args;
    }

    /// <summary>The same run without the files of the window: what a person would type to repeat it.</summary>
    public static string RunLine(string operation, string source, string target, IReadOnlyDictionary<string, string> changed)
    {
        var args = new List<string> { "run", "--operation", operation };
        if (source.Length > 0) { args.Add("--source"); args.Add(Paths.Short(source)); }
        if (target.Length > 0) { args.Add("--target"); args.Add(Paths.Short(target)); }
        foreach (var (name, value) in changed) { args.Add("--set"); args.Add(name + "=" + value); }
        return ConsoleLine(args);
    }

    public static Launch Make(IEnumerable<string> args) =>
        new() { Exe = Paths.Python, Args = new[] { "-u", Script }.Concat(args).ToList(), Env = Env };

    /// <summary>The files of the last run are cleared away and the values of the new one written; false when that did not work.</summary>
    public static bool Prepare(string valuesJson)
    {
        try
        {
            foreach (var file in new[] { ResultFile, StopFile })
                if (File.Exists(file)) File.Delete(file);
            File.WriteAllText(ParamsFile, valuesJson, new UTF8Encoding(false));
            return true;
        }
        catch (Exception ex)
        {
            Journal.Add(Lang.F("[окно] не запустилось: {0}", ex.Message));
            return false;
        }
    }

    /// <summary>Asks the running operation to stop. The operation sees the file itself.</summary>
    public static bool AskToStop()
    {
        try { File.WriteAllText(StopFile, DateTime.Now.ToString("O")); return true; }
        catch { return false; }
    }

    /// <summary>The service line of a run read; null when the line is an ordinary one.</summary>
    public static DoorEvent? Read(string line)
    {
        if (!line.StartsWith(Control, StringComparison.Ordinal)) return null;
        try
        {
            using var doc = JsonDocument.Parse(line[Control.Length..]);
            var root = doc.RootElement;
            static string Text(JsonElement owner, string name) => owner.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
            static double Number(JsonElement owner, string name, double none) => owner.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : none;
            if (root.TryGetProperty("started", out var started))
                return new DoorEvent { Kind = "started", Log = Text(started, "log"), ReportDir = Text(started, "report_dir") };
            if (root.TryGetProperty("finished", out var finished))
                return new DoorEvent { Kind = "finished", Outcome = Text(finished, "outcome"), Message = Text(finished, "message") };
            if (root.TryGetProperty("live", out var live) && live.ValueKind == JsonValueKind.String)
                return new DoorEvent { Kind = "live", Live = live.GetString() ?? "" };
            if (root.TryGetProperty("progress", out _))
                return new DoorEvent { Kind = "progress", Progress = Number(root, "progress", -1) };
            // A service line of a kind this window does not know yet: not for the journal either way.
            return new DoorEvent { Kind = "" };
        }
        catch { return new DoorEvent { Kind = "" }; }
    }

    /// <summary>The result file of the run that has just ended; null when the command did not get as far as writing it.</summary>
    public static RunResult? ReadResult()
    {
        try
        {
            if (!File.Exists(ResultFile)) return null;
            return JsonSerializer.Deserialize<RunResult>(File.ReadAllText(ResultFile), Json);
        }
        catch (Exception ex)
        {
            Journal.Add(Lang.F("[окно] итог операции не прочитан: {0}", ex.Message));
            return null;
        }
    }

    // ------------------------------------------------------------ short calls

    /// <summary>
    /// A call that answers at once - the manifest, the count of closed Excels: the command is run,
    /// its output read whole. Never throws: a command that could not be started answers with the
    /// code -1 and the reason.
    /// </summary>
    public static async Task<Reply> Call(IReadOnlyList<string> args, int timeoutMs = 120_000)
    {
        if (!Ready) return new Reply(-1, "", Trouble);
        var launch = Make(args);
        var info = new ProcessStartInfo(launch.Exe)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
            WorkingDirectory = Paths.Root,
        };
        foreach (var arg in launch.Args) info.ArgumentList.Add(arg);
        foreach (var (name, value) in launch.Env) info.Environment[name] = value;
        try
        {
            using var process = Process.Start(info) ?? throw new InvalidOperationException("the process was not created");
            process.StandardInput.Close();
            var output = process.StandardOutput.ReadToEndAsync();
            var errors = process.StandardError.ReadToEndAsync();
            var exited = process.WaitForExitAsync();
            if (await Task.WhenAny(exited, Task.Delay(timeoutMs)) != exited)
            {
                try { process.Kill(entireProcessTree: true); } catch { }
                return new Reply(-1, "", Lang.F("консольная команда не ответила за {0} с", timeoutMs / 1000));
            }
            return new Reply(process.ExitCode, await output, await errors);
        }
        catch (Exception ex)
        {
            return new Reply(-1, "", ex.Message);
        }
    }

    /// <summary>The manifest of the project, or the reason there is none.</summary>
    public static async Task<(Manifest? Manifest, string Trouble)> Describe()
    {
        var reply = await Call(new[] { "describe" });
        if (!reply.Ok) return (null, Lines(reply.Err.Length > 0 ? reply.Err : reply.Out));
        try { return (Manifest.Parse(reply.Out), ""); }
        catch (Exception ex) { return (null, ex.Message); }
    }

    /// <summary>
    /// Closes the Excel and Word the engine started and noted in the session folder: for an
    /// operation that was ended before it could quit them itself. Returns (closed, may be left).
    /// </summary>
    public static async Task<(int Stopped, int Lost)> StopOffice()
    {
        if (!Directory.Exists(OfficeNotes)) return (0, 0);
        var reply = await Call(new[] { "stop-office", "--session-dir", OfficeNotes }, 60_000);
        if (!reply.Ok) return (0, 0);
        try
        {
            using var doc = JsonDocument.Parse(reply.Out);
            int Count(string name) => doc.RootElement.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetInt32() : 0;
            return (Count("stopped"), Count("lost"));
        }
        catch { return (0, 0); }
    }

    static string Lines(string text) => string.Join(" ", text.Split('\n').Select(line => line.Trim()).Where(line => line.Length > 0));
}

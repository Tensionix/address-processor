using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace AudionAddressProcessor.Core;

/// <summary>
/// The questions a window asks while a person types - which sheets a workbook has, which
/// settlements match a name - answered by one process of the engine that stays up (`serve` of
/// address_cli.cmd): one JSON object a line in, one answer a line out. A command of its own for
/// each question would read the Rosstat registry again every time, about a second and a half. An
/// operation never runs here: it is a process of its own that STOP can end.
/// </summary>
public sealed class Server : IDisposable
{
    Process? _process;
    readonly object _gate = new();
    readonly Dictionary<long, TaskCompletionSource<JsonElement>> _waiting = new();
    long _next;
    bool _disposed;

    public static string Trouble => Door.Ready ? "" : Door.Trouble;

    /// <summary>The process of questions has been started and is up.</summary>
    public bool IsUp
    {
        get { lock (_gate) return _process is { HasExited: false }; }
    }

    void Ensure()
    {
        lock (_gate)
        {
            if (_disposed) throw new ObjectDisposedException(nameof(Server));
            if (_process is { HasExited: false }) return;
            var launch = Door.Make(new[] { "serve" });
            var info = new ProcessStartInfo(launch.Exe)
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardInputEncoding = new UTF8Encoding(false),
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
                WorkingDirectory = Paths.Root,
            };
            foreach (var arg in launch.Args) info.ArgumentList.Add(arg);
            foreach (var (name, value) in launch.Env) info.Environment[name] = value;
            var process = Process.Start(info) ?? throw new InvalidOperationException("the process was not created");
            process.OutputDataReceived += (_, e) => { if (e.Data is { Length: > 0 } line) Answer(line); };
            process.ErrorDataReceived += (_, e) => { if (e.Data is { Length: > 0 } text) _lastError = text; };
            process.EnableRaisingEvents = true;
            process.Exited += (_, _) => Fail(Lang.T("процесс вопросов к движку завершился") + (_lastError.Length > 0 ? ": " + _lastError : ""), process);
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            _process = process;
        }
    }

    void Answer(string line)
    {
        try
        {
            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement.Clone();
            if (!root.TryGetProperty("id", out var id) || id.ValueKind != JsonValueKind.Number) return;
            TaskCompletionSource<JsonElement>? waiting;
            lock (_gate)
            {
                if (!_waiting.Remove(id.GetInt64(), out waiting)) return;
            }
            waiting.TrySetResult(root);
        }
        catch { }
    }

    /// <summary>The last line the process of questions wrote to its error stream: what is told when it ends on its own.</summary>
    string _lastError = "";

    /// <summary>The process that asked is gone: its questions are answered with the reason. The end of an older process is not the end of this one.</summary>
    void Fail(string why, Process? who = null)
    {
        List<TaskCompletionSource<JsonElement>> all;
        lock (_gate)
        {
            if (who is not null && !ReferenceEquals(_process, who)) return;
            all = _waiting.Values.ToList();
            _waiting.Clear();
            _process = null;
        }
        foreach (var waiting in all) waiting.TrySetException(new InvalidOperationException(why));
    }

    /// <summary>One request and its answer; throws with the engine's own words when it says "ok": false.</summary>
    public async Task<JsonElement> Ask(JsonObject request, int timeoutMs = 90_000)
    {
        if (!Door.Ready) throw new InvalidOperationException(Door.Trouble);
        TaskCompletionSource<JsonElement> waiting = new(TaskCreationOptions.RunContinuationsAsynchronously);
        long id;
        lock (_gate)
        {
            Ensure();
            id = ++_next;
            _waiting[id] = waiting;
        }
        request["id"] = id;
        try
        {
            var line = request.ToJsonString(new JsonSerializerOptions { Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
            lock (_gate)
            {
                _process!.StandardInput.WriteLine(line);
                _process.StandardInput.Flush();
            }
        }
        catch (Exception ex)
        {
            lock (_gate) _waiting.Remove(id);
            Fail(ex.Message);
            throw new InvalidOperationException(ex.Message);
        }
        var done = await Task.WhenAny(waiting.Task, Task.Delay(timeoutMs));
        if (done != waiting.Task)
        {
            lock (_gate) _waiting.Remove(id);
            throw new TimeoutException(Lang.F("движок не ответил за {0} с", timeoutMs / 1000));
        }
        var answer = await waiting.Task;
        if (answer.TryGetProperty("ok", out var ok) && ok.ValueKind == JsonValueKind.False)
            throw new InvalidOperationException(answer.TryGetProperty("error", out var error) ? error.ToString() : "?");
        return answer;
    }

    static JsonObject Parse(string json) => JsonNode.Parse(json) as JsonObject ?? new JsonObject();

    /// <summary>The options of a field that has a list from a provider, for the values the form holds.</summary>
    public async Task<List<Option>> Options(string operation, string field, string valuesJson)
    {
        var answer = await Ask(new JsonObject
        {
            ["command"] = "options", ["operation"] = operation, ["field"] = field, ["values"] = Parse(valuesJson),
        });
        var options = new List<Option>();
        if (answer.TryGetProperty("options", out var list) && list.ValueKind == JsonValueKind.Array)
            foreach (var item in list.EnumerateArray())
                options.Add(JsonSerializer.Deserialize<Option>(item.GetRawText(), new JsonSerializerOptions
                {
                    PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower, PropertyNameCaseInsensitive = true,
                }) ?? new Option());
        return options;
    }

    /// <summary>An action of the OKTMO panel (address_cli.cmd oktmo --action …); the "result" of the answer.</summary>
    public async Task<JsonElement> Oktmo(string action, JsonObject? values = null, string kind = "region")
    {
        var answer = await Ask(new JsonObject
        {
            ["command"] = "oktmo", ["action"] = action, ["kind"] = kind, ["values"] = values ?? new JsonObject(),
        // Keys of a whole region are thousands of rows: no hurry that the engine could not keep.
        }, action is "add_scope_keys" or "add_candidate_keys" or "find_candidates" ? 600_000 : 90_000);
        return answer.TryGetProperty("result", out var result) ? result : default;
    }

    /// <summary>Only the lists built from the data are asked for again: a pin changed the order of a list.</summary>
    public async Task ForgetOptions()
    {
        try { await Ask(new JsonObject { ["command"] = "forget", ["what"] = "options" }); } catch { }
    }

    /// <summary>The Rosstat data changed: what was read of it, and the lists built from it, are old.</summary>
    public async Task Forget()
    {
        try { await Ask(new JsonObject { ["command"] = "forget" }); } catch { }
    }

    public void Dispose()
    {
        Process? process;
        lock (_gate)
        {
            _disposed = true;
            process = _process;
            _process = null;
        }
        if (process is null) return;
        try
        {
            if (!process.HasExited)
            {
                try { process.StandardInput.WriteLine("{\"command\":\"quit\"}"); process.StandardInput.Flush(); } catch { }
                if (!process.WaitForExit(1500)) process.Kill(entireProcessTree: true);
            }
        }
        catch { }
        finally { process.Dispose(); }
    }
}

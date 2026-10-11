using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;

namespace AudionAddressProcessor.Core;

public enum LogTone { Plain, Muted, Head, Good, Warn, Bad }

/// <summary>
/// The journal of the window. Two kinds of lines come to its panel. What the window says itself -
/// a run started, how it ended, what could not be done - also goes to the file of the day
/// (logs\gui-DATE.log) with its time. What an operation says is shown as the door printed it and
/// is not written again: every operation keeps its own journal in logs\, and the window names
/// that file when the run ends.
/// </summary>
public static class Journal
{
    /// <summary>Lines for the panel, in the order they came; raised on the thread that wrote them.</summary>
    public static event Action<IReadOnlyList<(string Text, LogTone Tone)>>? Lines;

    static string LogFile => Path.Combine(Paths.Logs, $"gui-{DateTime.Now:yyyyMMdd}.log");

    /// <summary>A line of the window: to the panel and to the file of the day.</summary>
    public static void Add(string line) => AddMany(new[] { line });

    public static void AddMany(IReadOnlyList<string> lines)
    {
        if (lines.Count == 0) return;
        var shown = new List<(string, LogTone)>(lines.Count);
        var file = new StringBuilder();
        var stamp = DateTime.Now.ToString("HH:mm:ss");
        foreach (var raw in lines)
        {
            var line = Lang.T(raw);
            shown.Add((line, Tone(line)));
            file.Append(stamp).Append("  ").AppendLine(line);
        }
        try { File.AppendAllText(LogFile, file.ToString(), Encoding.UTF8); } catch { }
        Lines?.Invoke(shown);
    }

    /// <summary>Lines of an operation: to the panel alone, as the door printed them.</summary>
    public static void Show(IReadOnlyList<string> lines)
    {
        if (lines.Count == 0) return;
        var shown = new List<(string, LogTone)>(lines.Count);
        foreach (var line in lines) shown.Add((line, Tone(line)));
        Lines?.Invoke(shown);
    }

    // The verdict of a run, as the window writes it: "===== Пересчитать в Word: готово · 0:19".
    static readonly Regex HeadGood = new(": (готово|done)( · |$)", RegexOptions.Compiled);
    static readonly Regex HeadWarn = new(": (готово с замечаниями|done with remarks|остановлено|stopped)( · |:|$)", RegexOptions.Compiled);
    static readonly Regex HeadBad = new(": (ошибка|failed|отказ до начала|rejected before the start|не запустилось|did not start)( · |$)", RegexOptions.Compiled);

    // What an operation says. The engine marks its lines at their start; red is only for what
    // really broke, or the journal frightens for no reason.
    static readonly Regex Bad = new(@"^\[(ERR|ERROR|FAIL|FAILED)\]|^ERROR\b|^Traceback|^\w*(Error|Exception): |не запустилось|did not start|нет файла|no such file|действие не вышло|did not work|не сохранилось|not saved|испорчен|is broken", RegexOptions.Compiled);
    static readonly Regex Warn = new(@"^\[(WARN|WARNING|CANCEL|REFUSED)\]|остановлено|cancelled by user|stopped by", RegexOptions.Compiled);
    static readonly Regex Good = new(@"^\[OK\]|^\[(COPIED|CREATED)\]", RegexOptions.Compiled);
    // The step of a pass: "[1/3] Processing: book.xlsx", "Stage 2: ..." - the headings of a run.
    static readonly Regex Step = new(@"^\[\d+/\d+\] ", RegexOptions.Compiled);
    // What an operation says of itself and of its way: read when something went wrong, quiet otherwise.
    static readonly Regex Muted = new(@"^> |^\[(SKIP|INFO|dev|CWD|CMD|EXIT|DELETE)\]|^Starting operation: |^Finished operation: |^Parameters: |^(программа|команда|program|command)\s*:", RegexOptions.Compiled);

    /// <summary>What colour a line is written in.</summary>
    public static LogTone Tone(string line)
    {
        var t = line.TrimEnd();
        if (t.Trim().Length == 0) return LogTone.Plain;
        if (t.StartsWith("====="))
        {
            if (HeadWarn.IsMatch(t)) return LogTone.Warn;
            if (HeadGood.IsMatch(t)) return LogTone.Good;
            if (HeadBad.IsMatch(t)) return LogTone.Bad;
            return LogTone.Head;
        }
        if (Bad.IsMatch(t)) return LogTone.Bad;
        if (Warn.IsMatch(t)) return LogTone.Warn;
        if (Good.IsMatch(t)) return LogTone.Good;
        if (Step.IsMatch(t)) return LogTone.Head;
        if (Muted.IsMatch(t)) return LogTone.Muted;
        if (t.StartsWith("[окно]") || t.StartsWith("[window]")) return LogTone.Muted;
        return LogTone.Plain;
    }
}

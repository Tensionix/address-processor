using System.Text.RegularExpressions;
using Avalonia.Controls;
using Avalonia.Controls.Documents;

namespace AudionAddressProcessor.Views;

/// <summary>
/// The live line of the journal in its colours. A stage of the alignment writes a bar that is
/// rewritten in place:
///
///     Stage 1:  62%|██████▏   | 31/50 [00:03&lt;00:02,  9.9it/s]
///
/// the percent is the accent, the bar and the brackets are quiet, the rest is plain. The line is the
/// operation's own (the engine writes it with tqdm); the window knows no stage by its name.
/// </summary>
public static class LiveLine
{
    static readonly Regex Parts = new(
        @"(?<percent>\b\d{1,3}%)|(?<bar>\|[^|]*\|)|(?<bracket>\[[^\]]*\])",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    public static void Paint(TextBlock block, string text)
    {
        var inlines = block.Inlines ??= new InlineCollection();
        inlines.Clear();
        void Add(string piece, string key)
        {
            if (piece.Length > 0) inlines.Add(new Run(piece) { Foreground = App.Ink(key) });
        }
        int at = 0;
        foreach (Match match in Parts.Matches(text))
        {
            Add(text[at..match.Index], "LogPlain");
            Add(match.Value, match.Groups["percent"].Success ? "Quasar" : "LogMuted");
            at = match.Index + match.Length;
        }
        Add(text[at..], "LogPlain");
    }
}

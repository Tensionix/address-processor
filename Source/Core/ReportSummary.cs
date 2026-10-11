using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

namespace AudionAddressProcessor.Core;

/// <summary>
/// The summary of the JSON report an operation writes: the rows the window before this one showed
/// (report_summary_rows of its app.py) - the counts of the run, the quality, the diagnostics, how full
/// the slots are, what the normaliser was set to. The report itself stays on the disk.
/// </summary>
public static class ReportSummary
{
    static readonly string[] Keys =
    {
        "mode", "action", "source_file_count", "raw_candidates", "scanned_values", "plausible_values", "accepted_candidates",
        "normalized_rows", "duplicate_rows", "rejected_rows", "appended_rows", "data_rows", "sorted_rows", "deconstructed_rows",
        "matched_unique_key_count", "missing_unique_key_count", "extra_unique_key_count",
    };

    public static List<(string Key, string Value)> Rows(JsonElement data, string fileName)
    {
        var rows = new List<(string, string)> { ("file", fileName) };
        if (data.ValueKind != JsonValueKind.Object) return rows;

        void Add(string key)
        {
            if (!data.TryGetProperty(key, out var value) || Empty(value)) return;
            rows.Add((key, Text(value)));
        }
        foreach (var key in Keys) Add(key);

        if (data.TryGetProperty("quality", out var quality) && quality.ValueKind == JsonValueKind.Object)
        {
            var coverage = quality.TryGetProperty("coverage_percent", out var c) ? Text(c) : null;
            var precision = quality.TryGetProperty("precision_percent", out var p) ? Text(p) : null;
            if (coverage is not null || precision is not null) rows.Add(("quality", $"coverage={coverage ?? "None"}%, precision={precision ?? "None"}%"));
        }
        if (data.TryGetProperty("address_diagnostics", out var diagnostics) && diagnostics.ValueKind == JsonValueKind.Object)
            rows.AddRange(Diagnostics(diagnostics));
        if (data.TryGetProperty("slot_fill", out var fill) && fill.ValueKind == JsonValueKind.Object)
            rows.AddRange(SlotFill(fill));

        JsonElement normalizer = default;
        if (data.TryGetProperty("normalizer", out var direct) && !Empty(direct)) normalizer = direct;
        else if (data.TryGetProperty("address_runtime", out var runtime) && runtime.ValueKind == JsonValueKind.Object && runtime.TryGetProperty("normalizer", out var inner)) normalizer = inner;
        if (normalizer.ValueKind == JsonValueKind.Object)
        {
            string Get(string name) => normalizer.TryGetProperty(name, out var v) && !Empty(v) ? Text(v) : "-";
            rows.Add(("normalizer", $"use_oktmo={Get("use_oktmo")}, TER={Get("subject_ter_hint")}, municipality={Get("municipality_hint")}"));
        }
        return rows.Take(40).ToList();
    }

    static IEnumerable<(string, string)> Diagnostics(JsonElement diagnostics)
    {
        if (diagnostics.TryGetProperty("total", out _))
        {
            yield return ("diagnostics", $"total={Field(diagnostics, "total")}, issues={Field(diagnostics, "issue_rows")}");
            yield break;
        }
        foreach (var property in diagnostics.EnumerateObject())
            if (property.Value.ValueKind == JsonValueKind.Object && property.Value.TryGetProperty("total", out _))
                yield return ($"diagnostics.{property.Name}", $"total={Field(property.Value, "total")}, issues={Field(property.Value, "issue_rows")}");
    }

    static IEnumerable<(string, string)> SlotFill(JsonElement fill)
    {
        string Line(JsonElement one) => $"rows={Field(one, "rows_total")}, complete={Field(one, "complete_rows")}, incomplete={Field(one, "incomplete_rows")}";
        if (fill.TryGetProperty("rows_total", out _))
        {
            yield return ("slot_fill", Line(fill));
            yield break;
        }
        foreach (var property in fill.EnumerateObject())
            if (property.Value.ValueKind == JsonValueKind.Object && property.Value.TryGetProperty("rows_total", out _))
                yield return ($"slot_fill.{property.Name}", Line(property.Value));
    }

    static string Field(JsonElement owner, string name) => owner.TryGetProperty(name, out var v) ? Text(v) : "None";

    static bool Empty(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.Null or JsonValueKind.Undefined => true,
        JsonValueKind.String => value.GetString() is null or "",
        JsonValueKind.Array => value.GetArrayLength() == 0,
        JsonValueKind.Object => !value.EnumerateObject().Any(),
        _ => false,
    };

    static string Text(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.String => value.GetString() ?? "",
        JsonValueKind.Number => value.GetRawText(),
        JsonValueKind.True => "True",
        JsonValueKind.False => "False",
        JsonValueKind.Null => "None",
        _ => value.GetRawText(),
    };
}

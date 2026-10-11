using System;
using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace AudionAddressProcessor.Core;

/// <summary>
/// config\window_settings.json: the look of the window and its sizes. The working folders are not
/// kept: every start begins with input and output of the project. The file is the state of one
/// machine - cleanup_project.cmd removes it and the repository does not carry it.
/// </summary>
public sealed class Settings
{
    /// <summary>The theme: "codedark" (Audion Code Dark, the one of the window before this one), "vault", "dark", "light".</summary>
    public string Look { get; set; } = "codedark";

    /// <summary>"" - none chosen yet. "ru" or "en" once the button was pressed.</summary>
    public string Lang { get; set; } = "";

    public int FontStep { get; set; }

    public double Width { get; set; }
    public double Height { get; set; }

    /// <summary>The width of the right column - the working folders, the result and the journal; 0 - the default share.</summary>
    public double Side { get; set; }

    [JsonIgnore]
    public string LanguageInUse => LanguageFor(Lang);

    /// <summary>
    /// The language of the window: the chosen one; with none chosen - Russian (the owner, 11.10.2026: the
    /// program is built on Russian addresses, so it opens in Russian whatever the system speaks).
    /// </summary>
    public static string LanguageFor(string chosen) => chosen == "en" ? "en" : "ru";

    static readonly JsonSerializerOptions Json = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true,
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    static string File_ => Path.Combine(Paths.Config, "window_settings.json");

    public static Settings Load() => (SafeFile.Read<Settings>(File_, Json) ?? new Settings()).Clean();

    Settings Clean()
    {
        Look = Look is "vault" or "dark" or "codedark" or "light" ? Look : "codedark";
        Lang ??= "";
        if (FontStep is < -1 or > 1) FontStep = 0;
        if (double.IsNaN(Side) || Side < 0) Side = 0;
        return this;
    }

    public void Save() => SafeFile.Write(File_, JsonSerializer.Serialize(this, Json));
}

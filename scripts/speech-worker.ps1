#Requires -Version 5.1
# Fixed local Windows voice. Text arrives as data, never PowerShell code or SSML.
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Speech
$voice = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $voice.SelectVoice('Microsoft Zira Desktop')
    $voice.Rate = 0
    $voice.Volume = 100
    $format = [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(
        16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
        [System.Speech.AudioFormat.AudioChannel]::Mono)
    @{ ready = $true; voice = $voice.Voice.Name; culture = $voice.Voice.Culture.Name;
       voice_id = $voice.Voice.Id;
       engine = [System.Speech.Synthesis.SpeechSynthesizer].Assembly.FullName;
       windows = [Environment]::OSVersion.Version.ToString() } | ConvertTo-Json -Compress
    while ($null -ne ($line = [Console]::ReadLine())) {
        $request = $line | ConvertFrom-Json
        $stream = [IO.MemoryStream]::new()
        try {
            $voice.SetOutputToAudioStream($stream, $format)
            $voice.Speak([string]$request.text)
            @{ pcm = [Convert]::ToBase64String($stream.ToArray()) } | ConvertTo-Json -Compress
        } finally { $stream.Dispose() }
    }
} finally { $voice.Dispose() }

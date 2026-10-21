<h1 align="center">
  <img src="https://raw.githubusercontent.com/qwersyk/Newelle/master/data/icons/hicolor/scalable/apps/io.github.qwersyk.Newelle.svg" alt="Newelle" width="192" height="192"/>
  <br>
  Newelle - Your Ultimate Virtual Assistant
</h1>
<p align="center">
    <a href="https://github.com/topics/newelle-extension">
      <picture>
        <source srcset="https://raw.githubusercontent.com/qwersyk/Assets/main/newelle-extension.svg" media="(prefers-color-scheme: light)">
        <source srcset="https://raw.githubusercontent.com/qwersyk/Assets/main/newelle-extension-dark.svg" media="(prefers-color-scheme: dark)">
        <img width="200" alt="Download on Flathub" src="https://raw.githubusercontent.com/qwersyk/Assets/main/newelle-extension.svg"/>
      </picture>
    </a>
    <a href="https://github.com/qwersyk/Newelle/wiki">
      <picture>
        <source srcset="https://raw.githubusercontent.com/qwersyk/Assets/main/newelle-wiki.svg" media="(prefers-color-scheme: light)">
        <source srcset="https://raw.githubusercontent.com/qwersyk/Assets/main/newelle-wiki-dark.svg" media="(prefers-color-scheme: dark)">
        <img width="200" alt="Wiki for Newelle" src="https://raw.githubusercontent.com/qwersyk/Assets/main/newelle-wiki.svg"/>
      </picture>
    </a>
	<a href="https://newelle.qsk.me/discord">
      <picture>
        <source srcset="https://raw.githubusercontent.com/qwersyk/Assets/main/discord.svg" media="(prefers-color-scheme: light)">
        <source srcset="https://raw.githubusercontent.com/qwersyk/Assets/main/discord-dark.svg" media="(prefers-color-scheme: dark)">
        <img width="200" alt="Join our discord" src="https://raw.githubusercontent.com/qwersyk/Assets/main/discord.svg"/>
      </picture>
    </a>
    <br>
</p>

https://github.com/user-attachments/assets/909edf0e-5a79-40c2-a3ef-cb5b2b18abfc

# Features


- 🎨 **Advanced Customization**: Tailor the application with a wide range of settings
- ✈️ **Connect Newelle to anything**: Interfaces allow you to control Newelle from Telegram, via API or anything else
- 🚀 **Flexible Model Support**: Choose from mutliple AI models and providers to fit your specific needs
- 📚 **Local models**: Download local models directly from Newelle, and run them using Llama.cpp or Ollama.
- 💻 **Terminal Command Exection**: Execute commands suggested by the AI on the fly
- 🧩 **Extensions**: Add your own functionalities and models to Newelle
- ✨ **Skills**: Newelle supports skills from Claude, Codex...
- 🛠 **Tools & MCP support**: Add tools via MCP servers or extensions, supporting tool search
- 🗣 **Voice support**: Chat hands free with Newelle, supporting many Speech To Text and TTS models (With wakeword support)
- 📞 **Call Mode**: Chat in real time with AI models
- 🧠 **Long Term Memory**: Remember conversations from previous chats
- 💼 **Chat with documents**: Chat with your own documents
- 🖼 **Image Generation**: Generate images directly in Newelle with stablediffusion or use third party services
- 🔎 **Web Search**: Provide reliable answers using Web Search
- 🌐 **Website Reading**: Scrape informations from websites by appending the prefix #https://.. in the prompt
- 🖍 **Dynamic Context Management**: Dynamically summarize and remove non relevant messages to fit in the context
- 🔓 **File Permissions**: Set permissions to which files to edit/read
- ⏰ **Scheduled Tasks**: Schedule tasks to run in the background
- 👤 **Profile Manager**: Create settings profiles and switch between them
- 📁 **Builtin File Manager**: Manage you files with the help of AI
- 📝 **Rich Formatting**: Supports both Markdown and LaTeX
- 💬 **Multichat**: Run multiple chats at the same time
- 🌳 **Chat Branching**: Create alternative versions of your chats strating from any message in one click
- ✏️ **Chat editing**: Edit or remove any message and manage your prompts easily
- 🗂 **Chat Folders**: Organize your chats into folders

<picture>
  <source srcset="screenshots/macos.png" media="(prefers-color-scheme: light)">
  <source srcset="screenshots/macos_b.png" media="(prefers-color-scheme: dark)">
  <img src="screenshots/macos.png" alt="screenshot">
</picture>

# Installation

Build from source on macOS:

```bash
/usr/bin/env bash macos/build_newelle_dmg.sh
```


## macOS build and checks

This fork includes upstream Newelle 1.6.0 and subsequent fixes through
[`d6ed29b`](https://github.com/qwersyk/Newelle/commit/d6ed29b), while keeping the
native macOS launcher, Command shortcuts, browser, terminal, and DMG packaging.

On an Apple Silicon Mac, install the build dependencies with Homebrew:

```bash
brew install python@3.13 gtk4 libadwaita gtksourceview5 pygobject3 \
  adwaita-icon-theme vte3 portaudio librsvg ffmpeg gettext
/usr/bin/env bash macos/build_newelle_dmg.sh
```

The installer is written to `dist/Newelle-1.6.0-macos-arm64.dmg`. The app includes
its Python and native dependencies, so Homebrew is only required for building.
Builds are ad-hoc signed and are not notarized.

Run the same compatibility checks used by GitHub Actions after building:

```bash
.venv-macos/bin/python -m unittest discover -s tests -v
dist/Newelle.app/Contents/MacOS/Newelle --smoke-test
```

The smoke test uses temporary settings and chats, blocks provider network
requests and dependency installation, and checks the main window, tabs,
settings, downloads, mini window, Voice Mode surface, and multiple windows.
It does not open the microphone or capture the screen. Recording and screenshot
features require access in macOS System Settings > Privacy & Security.

For future updates, merge `qwersyk/Newelle`'s `master` branch into a working
branch in this repository and run the macOS build and checks before merging.
Keep the `macos/` packaging and platform compatibility code when resolving
conflicts. Changes to this fork do not require changes to the upstream repository.


### macOS 27.2 window dragging

macOS 27.2 has a reported intermittent failure in the native drag handoff used
by GTK. On that OS version this fork tracks header drags inside the app for
both main and settings windows. This preserves normal window movement, but
native edge snapping and dragging through Mission Control are not provided
by the compatibility path. Other macOS versions keep the native drag path.
Set `NEWELLE_MANUAL_WINDOW_DRAG=0` to disable the workaround, or `1` to enable
it explicitly when testing another affected OS build.

def get_css() -> str:
    """
    Returns the CSS styling for the application
    """
    return """
    .log-view { /* removed - no embedded log */ }
    /* Minimal theme for the main banner/status */
    .status-banner {
        margin-top: 6px;
        margin-bottom: 10px;
    }
    .status-banner.status-up { color: #ffffff; }
    /* status-ok styling removed to avoid green color */
    .status-banner.status-err { color: #ff4d4f; }
    .tiny-link { font-size: 10px; padding: 0 4px; opacity: 0.85; }
    .ansi-bold     { font-weight: bold; }
    .ansi-dim      { opacity: 0.7; }
    .ansi-italic   { font-style: italic; }
    .ansi-underline{ text-decoration: underline; }
    .ansi-red      { color: #ff5555; }
    .ansi-green    { color: #50fa7b; }
    .ansi-yellow   { color: #f1fa8c; }
    .ansi-blue     { color: #8be9fd; }
    .ansi-magenta  { color: #ff79c6; }
    .ansi-cyan     { color: #66d9ef; }
    .ansi-white    { color: #f8f8f2; }
    .ansi-bright-black { color: #6272a4; }
    .ansi-bright-red { color: #ff6e6e; }
    .ansi-bright-green { color: #69ff94; }
    .ansi-bright-yellow { color: #ffffa5; }
    .ansi-bright-blue { color: #9aedfe; }
    .ansi-bright-magenta { color: #ff92df; }
    .ansi-bright-cyan { color: #82e9ff; }
    .ansi-bright-white { color: #ffffff; }
    """

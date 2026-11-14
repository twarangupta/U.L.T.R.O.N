import win32com.client

s = win32com.client.Dispatch("SAPI.SpVoice")
text = '<pitch absmiddle="-5">Hello, I am ULTRON. System online.</pitch>'
s.Speak(text)

import app
import db

# Make a dummy project and chat
proj = db.create_project("test_proj", "Test")
chat = db.create_chat(proj, "test_chat")

ai_resp = """Here is a simple HTML button:
```html
<button>Click me!</button>
```

And an image:
![Mascot](http://example.com/mascot.png)
"""

node_id = app.extract_and_save_artifacts(ai_resp, proj, chat)
arts = db.list_artifacts(proj)
for a in arts:
    print(a)

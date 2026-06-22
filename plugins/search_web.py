#!/usr/bin/env python3
import sys
import urllib.request
import urllib.parse
import json

def search(query):
    # Simplified search using duckduckgo lite or similar via simple API or HTML parsing
    # For MVP backend robustness, we will use a free API like DDG
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
            # Simple manual parse of DDG HTML
            results = []
            parts = html.split('class="result__snippet')
            for part in parts[1:6]:  # Top 5 results
                try:
                    snippet = part.split('href="', 1)[1]
                    link = snippet.split('"', 1)[0]
                    text = part.split('>', 1)[1].split('</a>', 1)[0].replace('<b>', '').replace('</b>', '')
                    results.append(f"Link: {link}\nSnippet: {text.strip()}\n")
                except:
                    pass
            
            if results:
                print(f"--- Top 5 Web Search Results for '{query}' ---")
                print("\n".join(results))
            else:
                print("No clear snippets found. Please write a more advanced parser.")
    except Exception as e:
        print(f"Search error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        search(" ".join(sys.argv[1:]))
    else:
        print("Usage: python3 search_web.py <query>")

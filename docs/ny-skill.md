# Så lägger du till en ny skill

1. Skapa en mapp under `skills/`. Mappnamnet ska skrivas med **gemener och bindestreck**,
   till exempel `skapa-prov`. Inga mellanslag, understreck eller stora bokstäver.
2. Skapa filen `SKILL.md` i mappen (exakt så, med stora bokstäver). Börja filen med:

   ```yaml
   ---
   name: skapa-prov            # samma som mappnamnet
   title: Skapa prov           # namnet som lärarna ser
   description: >-
     Vad skillen gör. Använd när läraren vill ... (skriv ord som läraren
     faktiskt använder, max cirka 150 ord).
   version: 1.0.0
   updated: 2026-11-07
   owner: Förnamn Efternamn
   ---
   ```

3. Skriv instruktionen under blocket. Håll den under 500 rader och helst under 10 000 tecken.
4. Längre underlag lägger du i `references/` (direkt i mappen, inga undermappar). Filer som lärare
   ska kunna ladda ner, till exempel mallar, lägger du i `assets/`. En referensfil får inte länka
   vidare till en annan referensfil.
5. Avsluta `SKILL.md` med en versionshistorik:

   ```markdown
   ## CHANGELOG

   - 2026-11-07 – 1.0.0: Första versionen.
   ```

6. Öppna en pull request. Bygget kontrollerar allt och säger tydligt vad som är fel.

## Ändra en skill

Höj alltid `version` och sätt `updated` till dagens datum:

- **1.0.0 → 1.0.1**: stavfel eller liten rättning.
- **1.0.0 → 1.1.0**: nytt innehåll.
- **1.0.0 → 2.0.0**: skillen beter sig annorlunda, eller något har tagits bort.

Lägg till en rad i versionshistoriken.

## Ta bort en skill

Ta inte bort mappen. Flytta den till `skills/_arkiv/` – då försvinner den från webbplatsen men
finns kvar i repot. Har skillen bytt namn kan du lägga till den gamla adressen i `redirects.json`.

## Aldrig

- Elevers namn, personnummer eller annan elevdata.
- Facit eller svar till prov.
- Ändringar direkt i Gemini, ChatGPT eller Copilot. Allt ändras här.

# Interviewer Accents

Sarah remains the female interviewer with the existing portrait. Before starting,
select Indian, American, British, Australian, Canadian, or Singapore English and
use **Preview voice** to hear the regional voice. The selection is fixed for the
session and stored with its history.

## Reliable Cross-Device Speech

Configure an Azure Speech resource in the server environment:

```text
JOB_AGENT_AZURE_SPEECH_KEY=your-resource-key
JOB_AGENT_AZURE_SPEECH_REGION=your-resource-region
```

Restart the server after setting the variables. Keep credentials server-side;
never commit them. These are environment variables: creating a `.env` file alone
does not load it into this application's process.

| Accent | Locale | Female neural voice |
| --- | --- | --- |
| Indian | en-IN | Neerja |
| American | en-US | Jenny |
| British | en-GB | Sonia |
| Australian | en-AU | Natasha |
| Canadian | en-CA | Clara |
| Singapore | en-SG | Luna |

Voice identifiers follow the [Azure Speech language support table](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support).
These are regional English voices, not a guarantee of every local dialect.

Without Azure, speech is available only when the browser exposes a known female
voice with the exact selected locale. The application never substitutes an
American voice for another country or guesses the gender of an unknown voice.
Unavailable speech is shown explicitly; text-based interviews remain available.

The authenticated catalog endpoint is `GET /api/mock-interview/accents`.
The authenticated preview endpoint is `POST /api/mock-interview/speech/preview`.
Previews use fixed server-owned text; interview speech uses the saved session's
region and questions. Azure availability and audio quality must be tested with a
real configured resource before deployment.

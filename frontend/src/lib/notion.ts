import { Client } from "@notionhq/client";
import type { Scene, Beat } from "./scenes";

// ---------------------------------------------------------------------------
// Singleton Notion client
// ---------------------------------------------------------------------------

let _client: Client | null = null;

function getNotionClient(): Client {
  if (!_client) {
    const token = process.env.NOTION_TOKEN;
    if (!token) {
      throw new Error("NOTION_TOKEN environment variable is not set");
    }
    _client = new Client({ auth: token });
  }
  return _client;
}

function getDatabaseId(): string {
  const id = process.env.NOTION_DATABASE_ID;
  if (!id) {
    throw new Error("NOTION_DATABASE_ID environment variable is not set");
  }
  return id;
}

// Cache the data source ID (v5 SDK uses dataSources instead of databases.query)
let _dataSourceId: string | null = null;

/**
 * Resolve the data_source_id for the Scenes database.
 * In @notionhq/client v5, queries go through dataSources.query
 * rather than databases.query.
 */
async function getDataSourceId(): Promise<string> {
  if (_dataSourceId) return _dataSourceId;

  const notion = getNotionClient();
  const databaseId = getDatabaseId();

  const db = await notion.databases.retrieve({ database_id: databaseId });
  const dataSources = (db as Record<string, unknown>).data_sources as
    | Array<{ id: string }>
    | undefined;

  if (!dataSources || dataSources.length === 0) {
    throw new Error(
      `No data sources found for database ${databaseId}. ` +
        "Make sure the database is shared with your integration."
    );
  }

  _dataSourceId = dataSources[0].id;
  return _dataSourceId;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Extract plain text from a Notion rich_text array. */
function richTextToPlain(
  richText: Array<{ plain_text: string }>
): string {
  return richText.map((t) => t.plain_text).join("");
}

function chunkText(text: string, size = 1800): Array<{ text: { content: string } }> {
  const chunks: Array<{ text: { content: string } }> = [];
  for (let i = 0; i < text.length; i += size) {
    chunks.push({ text: { content: text.slice(i, i + size) } });
  }
  return chunks;
}

// ---------------------------------------------------------------------------
// Create
// ---------------------------------------------------------------------------

/**
 * Create a scene page in Notion.
 * - Properties: Name, Scene ID, AI Character, Actor Label, Voice ID, Status
 * - Page body: a code block containing beats JSON
 */
export async function createSceneInNotion(scene: Scene): Promise<void> {
  const notion = getNotionClient();
  const databaseId = getDatabaseId();

  const aiCharacter = scene.characters?.AI ?? "";
  const actorLabel = scene.characters?.ACTOR ?? "";
  const voiceId = scene.voice?.ai_voice_id ?? "";

  await notion.pages.create({
    parent: { database_id: databaseId },
    properties: {
      Name: { title: [{ text: { content: scene.title } }] },
      "Scene ID": { rich_text: [{ text: { content: scene.scene_id } }] },
      "AI Character": { rich_text: [{ text: { content: aiCharacter } }] },
      "Actor Label": { rich_text: [{ text: { content: actorLabel } }] },
      "Voice ID": { rich_text: [{ text: { content: voiceId } }] },
      Status: { select: { name: "IDLE" } },
    },
    children: [
      {
        object: "block" as const,
        type: "code" as const,
        code: {
          rich_text: chunkText(JSON.stringify(scene.beats)),
          language: "json",
          caption: [{ text: { content: "beats" } }],
        },
      },
    ],
  });
}

// ---------------------------------------------------------------------------
// Read
// ---------------------------------------------------------------------------

/**
 * Load a scene from Notion by scene_id.
 * Queries the database for a page whose "Scene ID" matches,
 * then reads its children to extract the beats JSON code block.
 */
export async function loadSceneFromNotion(sceneId: string): Promise<Scene> {
  const notion = getNotionClient();
  const dataSourceId = await getDataSourceId();

  // Query for the page with matching Scene ID
  const queryResult = await notion.dataSources.query({
    data_source_id: dataSourceId,
    filter: {
      property: "Scene ID",
      rich_text: { equals: sceneId },
    },
    page_size: 1,
  });

  if (queryResult.results.length === 0) {
    throw new Error(`Scene '${sceneId}' not found in Notion.`);
  }

  const page = queryResult.results[0] as Record<string, unknown>;
  const pageId = page.id as string;
  const props = page.properties as Record<string, Record<string, unknown>>;

  // Extract properties
  const title = richTextToPlain(
    (props.Name as { title: Array<{ plain_text: string }> }).title
  );
  const aiCharacter = richTextToPlain(
    (props["AI Character"] as { rich_text: Array<{ plain_text: string }> })
      .rich_text
  );
  const actorLabel = richTextToPlain(
    (props["Actor Label"] as { rich_text: Array<{ plain_text: string }> })
      .rich_text
  );
  const voiceId = richTextToPlain(
    (props["Voice ID"] as { rich_text: Array<{ plain_text: string }> })
      .rich_text
  );

  // Read page children to find the beats code block
  const children = await notion.blocks.children.list({ block_id: pageId });
  let beats: Beat[] = [];

  for (const block of children.results) {
    const b = block as Record<string, unknown>;
    if (b.type === "code") {
      const codeBlock = b.code as {
        caption: Array<{ plain_text: string }>;
        rich_text: Array<{ plain_text: string }>;
      };
      const caption = codeBlock.caption
        ?.map((c) => c.plain_text)
        .join("")
        .toLowerCase();
      if (caption === "beats") {
        const json = richTextToPlain(codeBlock.rich_text);
        beats = JSON.parse(json) as Beat[];
        break;
      }
    }
  }

  return {
    scene_id: sceneId,
    title,
    characters: { AI: aiCharacter, ACTOR: actorLabel },
    voice: { ai_voice_id: voiceId },
    beats,
  };
}

// ---------------------------------------------------------------------------
// Update
// ---------------------------------------------------------------------------

/**
 * Update the Status property of a scene in Notion.
 */
export async function updateSceneStatusInNotion(
  sceneId: string,
  status: string
): Promise<void> {
  const notion = getNotionClient();
  const dataSourceId = await getDataSourceId();

  const queryResult = await notion.dataSources.query({
    data_source_id: dataSourceId,
    filter: {
      property: "Scene ID",
      rich_text: { equals: sceneId },
    },
    page_size: 1,
  });

  if (queryResult.results.length === 0) {
    throw new Error(`Scene '${sceneId}' not found in Notion.`);
  }

  const pageId = queryResult.results[0].id;
  await notion.pages.update({
    page_id: pageId,
    properties: {
      Status: { select: { name: status } },
    },
  });
}

// ---------------------------------------------------------------------------
// List
// ---------------------------------------------------------------------------

/**
 * List all scenes from the Notion database (metadata only, no beats).
 */
export async function listScenesFromNotion(): Promise<
  Array<{
    scene_id: string;
    title: string;
    status: string;
    ai_character: string;
  }>
> {
  const notion = getNotionClient();
  const dataSourceId = await getDataSourceId();

  const queryResult = await notion.dataSources.query({
    data_source_id: dataSourceId,
    sorts: [{ timestamp: "created_time", direction: "descending" }],
  });

  return queryResult.results.map((page: Record<string, unknown>) => {
    const props = page.properties as Record<
      string,
      Record<string, unknown>
    >;
    return {
      scene_id: richTextToPlain(
        (props["Scene ID"] as { rich_text: Array<{ plain_text: string }> })
          .rich_text
      ),
      title: richTextToPlain(
        (props.Name as { title: Array<{ plain_text: string }> }).title
      ),
      status:
        (props.Status as { select: { name: string } | null }).select?.name ??
        "IDLE",
      ai_character: richTextToPlain(
        (props["AI Character"] as { rich_text: Array<{ plain_text: string }> })
          .rich_text
      ),
    };
  });
}

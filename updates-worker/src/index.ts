import announcements from "../../docs/announcements.json";
import planContent from "../../docs/plan-content.json";

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400"
  };
}

function json(data: unknown) {
  return new Response(JSON.stringify(data, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=300",
      ...corsHeaders()
    }
  });
}

export default {
  fetch(request: Request) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: corsHeaders()
      });
    }

    if (request.method !== "GET") {
      return new Response("Method not allowed", { status: 405, headers: corsHeaders() });
    }

    if (url.pathname === "/announcements.json") {
      return json(announcements);
    }

    if (url.pathname === "/plan-content.json") {
      return json(planContent);
    }

    return new Response("Not found", { status: 404, headers: corsHeaders() });
  }
};

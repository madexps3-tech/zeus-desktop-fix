#include "sierrachart.h"
#include <cstdio>
#include <cstring>
#include <ctime>

SCDLLName("ZeusMboFlags")

struct OrderSnap { uint64_t id; double qty; double price; int bid; };
struct MboState { OrderSnap prev[400]; int prevCount; double sweepUntil; double icebergUntil; double pulledUntil; };

static int RootFromSymbol(const SCString& symbol, char* root, int rootSize)
{
    const char* text = symbol.GetChars();
    if (std::strstr(text, "GC") != nullptr) std::strncpy(root, "GC", rootSize);
    else if (std::strstr(text, "NQ") != nullptr) std::strncpy(root, "NQ", rootSize);
    else if (std::strstr(text, "CL") != nullptr) std::strncpy(root, "CL", rootSize);
    else return 0;
    root[rootSize - 1] = 0;
    return 1;
}

static void CollectSide(SCStudyInterfaceRef sc, int bidSide, int levels, OrderSnap* rows, int& count)
{
    const int kMaxOrders = 16;
    n_ACSIL::s_MarketOrderData orders[kMaxOrders];
    if (levels > 8) levels = 8;
    for (int level = 0; level < levels && count < 400; ++level)
    {
        s_MarketDepthEntry entry;
        if (bidSide) sc.GetBidMarketDepthEntryAtLevel(entry, level);
        else sc.GetAskMarketDepthEntryAtLevel(entry, level);
        int ticks = sc.Round(entry.AdjustedPrice / sc.TickSize);
        int found = bidSide ? sc.GetBidMarketLimitOrdersForPrice(ticks, kMaxOrders, orders) : sc.GetAskMarketLimitOrdersForPrice(ticks, kMaxOrders, orders);
        for (int i = 0; i < found && count < 400; ++i)
        {
            rows[count].id = orders[i].OrderID;
            rows[count].qty = orders[i].OrderQuantity;
            rows[count].price = entry.AdjustedPrice;
            rows[count].bid = bidSide;
            ++count;
        }
    }
}

SCSFExport scsf_ZeusMboFlags(SCStudyInterfaceRef sc)
{
    if (sc.SetDefaults)
    {
        sc.GraphName = "ZEUS MBO Flags";
        sc.StudyDescription = "Writes sweep, iceberg, and pulled-size flags for GC, NQ, and CL. Does not trade.";
        sc.AutoLoop = 0;
        sc.UsesMarketDepthData = 1;
        sc.UpdateAlways = 1;
        sc.FreeDLL = 0;
        return;
    }
    char root[8] = {};
    if (!RootFromSymbol(sc.Symbol, root, sizeof root)) return;
    MboState* state = static_cast<MboState*>(sc.GetPersistentPointer(1));
    if (state == nullptr)
    {
        state = static_cast<MboState*>(sc.AllocateMemory(sizeof(MboState)));
        if (state == nullptr) return;
        std::memset(state, 0, sizeof(MboState));
        sc.SetPersistentPointer(1, state);
    }
    OrderSnap current[400];
    int count = 0;
    CollectSide(sc, 1, sc.GetBidMarketDepthNumberOfLevels(), current, count);
    CollectSide(sc, 0, sc.GetAskMarketDepthNumberOfLevels(), current, count);
    const double now = static_cast<double>(std::time(nullptr));
    const double tradePrice = sc.LastTradePrice;
    const double large = (std::strcmp(root, "NQ") == 0) ? 30.0 : 10.0;
    const double tick = sc.TickSize > 0 ? sc.TickSize : 0.01;
    for (int oldIndex = 0; oldIndex < state->prevCount; ++oldIndex)
    {
        const OrderSnap& oldOrder = state->prev[oldIndex];
        const OrderSnap* match = nullptr;
        for (int newIndex = 0; newIndex < count; ++newIndex)
        {
            if (current[newIndex].id == oldOrder.id) { match = &current[newIndex]; break; }
        }
        const bool tradedHere = std::fabs(oldOrder.price - tradePrice) <= tick * 2.0;
        if (match == nullptr)
        {
            if (tradedHere && sc.LastTradeQuantity > 0) state->sweepUntil = now + 60.0;
            else if (oldOrder.qty >= large) state->pulledUntil = now + 60.0;
            continue;
        }
        if (oldOrder.qty >= large && match->qty < oldOrder.qty * 0.7 && tradedHere) state->icebergUntil = now + 60.0;
        if (oldOrder.qty >= large && match->qty >= oldOrder.qty * 0.9 && tradedHere && state->icebergUntil > now) state->icebergUntil = now + 60.0;
    }
    state->prevCount = count;
    if (count > 0) std::memcpy(state->prev, current, sizeof(OrderSnap) * static_cast<size_t>(count));
    SCString path = sc.DataFilesFolder();
    path.AppendFormat("zeus_mbo_%s.json", root);
    FILE* file = std::fopen(path.GetChars(), "wb");
    if (file == nullptr) return;
    std::fprintf(file, "{\"source\":\"SIERRA_ACSIL_MBO\",\"symbol\":\"%s\",\"sweep_consumed\":%d,\"iceberg_refresh\":%d,\"size_pulled\":%d}\n", root, state->sweepUntil >= now ? 1 : 0, state->icebergUntil >= now ? 1 : 0, state->pulledUntil >= now ? 1 : 0);
    std::fclose(file);
}

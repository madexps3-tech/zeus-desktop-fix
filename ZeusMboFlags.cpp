#include "sierrachart.h"
#include <cstdio>
#include <cstring>
#include <ctime>
#include <map>
#include <vector>

SCDLLName("ZeusMboFlags")

struct OrderSnap { uint64_t id; double qty; double price; int bid; };
struct MboState { OrderSnap prev[400]; int prevCount; double sweepUntil; double icebergUntil; double pulledUntil; };

struct ValueArea { int have; double poc; double vah; double val; };

static bool HasRoot(const char* text, const char* root)
{
    const char* found = std::strstr(text, root);
    if (found == nullptr) return false;
    if (found != text && std::isalpha(static_cast<unsigned char>(found[-1]))) return false;
    return true;
}

static int RootFromSymbol(const SCString& symbol, char* root, int rootSize)
{
    const char* text = symbol.GetChars();
    const char* pairs[][2] = {
        {"MGC", "GC"}, {"SIL", "SI"}, {"MNQ", "NQ"}, {"MCL", "CL"},
        {"M6E", "6E"}, {"M6J", "6J"}, {"MBT", "MBT"},
        {"BTC", "BTC"}, {"GC", "GC"}, {"SI", "SI"}, {"NQ", "NQ"},
        {"CL", "CL"}, {"6E", "6E"}, {"6J", "6J"},
    };
    for (unsigned int index = 0; index < sizeof(pairs) / sizeof(pairs[0]); ++index)
    {
        if (!HasRoot(text, pairs[index][0])) continue;
        std::strncpy(root, pairs[index][1], static_cast<size_t>(rootSize));
        root[rootSize - 1] = 0;
        return 1;
    }
    return 0;
}

static ValueArea SessionValue(SCStudyInterfaceRef sc)
{
    ValueArea area = {0, 0.0, 0.0, 0.0};
    c_VAPContainer* vap = sc.VolumeAtPriceForBars;
    if (vap == nullptr || sc.ArraySize < 1 || sc.TickSize <= 0) return area;
    const int last = sc.ArraySize - 1;
    const SCDateTime sessionStart = sc.GetTradingDayStartDateTimeOfBar(sc.BaseDateTimeIn[last]);
    std::map<int, unsigned int> volumeAtTick;
    unsigned int total = 0;
    for (int bar = last; bar >= 0; --bar)
    {
        if (sc.BaseDateTimeIn[bar] < sessionStart) break;
        const int levels = vap->GetSizeAtBarIndex(bar);
        for (int level = 0; level < levels; ++level)
        {
            s_VolumeAtPriceV2* row = nullptr;
            if (!vap->GetVAPElementAtIndex(bar, level, &row) || row == nullptr || row->Volume == 0) continue;
            volumeAtTick[row->PriceInTicks] += row->Volume;
            total += row->Volume;
        }
    }
    if (total == 0 || volumeAtTick.empty()) return area;
    std::vector<std::pair<int, unsigned int>> prices(volumeAtTick.begin(), volumeAtTick.end());
    int pocIndex = 0;
    for (int index = 1; index < static_cast<int>(prices.size()); ++index)
    {
        if (prices[index].second > prices[pocIndex].second) pocIndex = index;
    }
    int lowIndex = pocIndex;
    int highIndex = pocIndex;
    unsigned int covered = prices[pocIndex].second;
    const unsigned int need = static_cast<unsigned int>(total * 0.70);
    while (covered < need && (lowIndex > 0 || highIndex + 1 < static_cast<int>(prices.size())))
    {
        const unsigned int below = lowIndex > 0 ? prices[lowIndex - 1].second : 0;
        const unsigned int above = highIndex + 1 < static_cast<int>(prices.size()) ? prices[highIndex + 1].second : 0;
        if (below == 0 && above == 0) break;
        if (above >= below)
        {
            ++highIndex;
            covered += prices[highIndex].second;
        }
        else
        {
            --lowIndex;
            covered += prices[lowIndex].second;
        }
    }
    area.have = 1;
    area.poc = prices[pocIndex].first * sc.TickSize;
    area.val = prices[lowIndex].first * sc.TickSize;
    area.vah = prices[highIndex].first * sc.TickSize;
    return area;
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
        sc.StudyDescription = "Writes the session point of control, value area, and the sweep flags. Does not trade.";
        sc.AutoLoop = 0;
        sc.MaintainVolumeAtPriceData = 1;
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
            if (tradedHere) state->sweepUntil = now + 60.0;
            else if (oldOrder.qty >= large) state->pulledUntil = now + 60.0;
            continue;
        }
        if (oldOrder.qty >= large && match->qty < oldOrder.qty * 0.7 && tradedHere) state->icebergUntil = now + 60.0;
        if (oldOrder.qty >= large && match->qty >= oldOrder.qty * 0.9 && tradedHere && state->icebergUntil > now) state->icebergUntil = now + 60.0;
    }
    state->prevCount = count;
    if (count > 0) std::memcpy(state->prev, current, sizeof(OrderSnap) * static_cast<size_t>(count));
    SCString path;
    path.Format("%szeus_mbo_%s.json", sc.DataFilesFolder().GetChars(), root);
    FILE* file = std::fopen(path.GetChars(), "wb");
    if (file == nullptr) return;
    const ValueArea area = SessionValue(sc);
    if (area.have)
    {
        std::fprintf(file, "{\"source\":\"SIERRA_ACSIL_MBO\",\"symbol\":\"%s\",\"sweep_consumed\":%d,\"iceberg_refresh\":%d,\"size_pulled\":%d,\"poc\":%.10g,\"vah\":%.10g,\"val\":%.10g,\"last\":%.10g}\n", root, state->sweepUntil >= now ? 1 : 0, state->icebergUntil >= now ? 1 : 0, state->pulledUntil >= now ? 1 : 0, area.poc, area.vah, area.val, tradePrice);
    }
    else
    {
        std::fprintf(file, "{\"source\":\"SIERRA_ACSIL_MBO\",\"symbol\":\"%s\",\"sweep_consumed\":%d,\"iceberg_refresh\":%d,\"size_pulled\":%d,\"poc\":null,\"vah\":null,\"val\":null}\n", root, state->sweepUntil >= now ? 1 : 0, state->icebergUntil >= now ? 1 : 0, state->pulledUntil >= now ? 1 : 0);
    }
    std::fclose(file);
}

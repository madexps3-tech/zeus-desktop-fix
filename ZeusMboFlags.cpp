#include "sierrachart.h"
#include <cstdio>
#include <cstring>
#include <ctime>
#include <map>
#include <vector>

SCDLLName("ZeusMboFlags")

struct OrderSnap { uint64_t id; double qty; double price; int bid; };
struct IceLevel { int active; double price; int bid; int refills; double until; double peak; };
struct MboState { OrderSnap prev[400]; int prevCount; double sweepUntil; double icebergUntil; double pulledUntil; IceLevel bidIce; IceLevel askIce; int primaryBid; };
struct LevelQty { double price; double qty; int bid; };
struct IceWatch { double price; double qty; double refilled; int bid; int active; };
struct ShownIce { double price; double qty; double refilled; int bid; };
struct IceBook { int ready; double lastSales; int count; int shown; IceWatch row[64]; ShownIce out[8]; };

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
        {"M6E", "6E"}, {"M6J", "6J"}, {"MBT", "MBT"}, {"QG", "NG"},
        {"FDAX", "DAX"}, {"FDXM", "DAX"},
        {"BTC", "BTC"}, {"GC", "GC"}, {"SI", "SI"}, {"NQ", "NQ"},
        {"CL", "CL"}, {"6E", "6E"}, {"6J", "6J"}, {"NG", "NG"},
        {"DAX", "DAX"},
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

static void TradeDelta(SCStudyInterfaceRef sc, double& buy5, double& buy60)
{
    buy5 = 0.0;
    buy60 = 0.0;
    c_SCTimeAndSalesArray sales;
    sc.GetTimeAndSales(sales);
    const double now = sc.CurrentSystemDateTime.GetAsDouble();
    const double second = 1.0 / 86400.0;
    for (int index = sales.Size() - 1; index >= 0; --index)
    {
        const s_TimeAndSales& trade = sales[index];
        if (trade.Volume <= 0) continue;
        const double age = (now - trade.DateTime.GetAsDouble()) / second;
        if (age > 60.0) break;
        if (age < 0.0) continue;
        double signedVolume = 0.0;
        if (trade.Type == SC_TS_ASK) signedVolume = trade.Volume;
        else if (trade.Type == SC_TS_BID) signedVolume = -static_cast<double>(trade.Volume);
        else continue;
        buy60 += signedVolume;
        if (age <= 5.0) buy5 += signedVolume;
    }
}

static bool LadderRoot(const char* root)
{
    return std::strcmp(root, "GC") == 0 || std::strcmp(root, "CL") == 0 || std::strcmp(root, "NQ") == 0;
}

static void WriteMarks(FILE* file, SCStudyInterfaceRef sc, const char* root, double tradePrice)
{
    if (!LadderRoot(root) || sc.VolumeAtPriceForBars == nullptr || sc.TickSize <= 0.0 || sc.ArraySize < 1)
    {
        std::fprintf(file, "\"ladder\":null,\"stack\":null,\"unfinished_high\":null,\"unfinished_low\":null,");
        return;
    }
    c_VAPContainer* vap = sc.VolumeAtPriceForBars;
    const int last = sc.ArraySize - 1;
    const SCDateTime sessionStart = sc.GetTradingDayStartDateTimeOfBar(sc.BaseDateTimeIn[last]);
    std::map<int, std::pair<unsigned int, unsigned int>> atTick;
    std::map<int, std::pair<unsigned int, unsigned int>> closedTick;
    for (int bar = last; bar >= 0; --bar)
    {
        if (sc.BaseDateTimeIn[bar] < sessionStart) break;
        const int levels = vap->GetSizeAtBarIndex(bar);
        for (int level = 0; level < levels; ++level)
        {
            s_VolumeAtPriceV2* row = nullptr;
            if (!vap->GetVAPElementAtIndex(bar, level, &row) || row == nullptr) continue;
            atTick[row->PriceInTicks].first += row->BidVolume;
            atTick[row->PriceInTicks].second += row->AskVolume;
            if (bar == last) continue;
            closedTick[row->PriceInTicks].first += row->BidVolume;
            closedTick[row->PriceInTicks].second += row->AskVolume;
        }
    }
    if (atTick.empty())
    {
        std::fprintf(file, "\"ladder\":[],\"stack\":null,\"unfinished_high\":null,\"unfinished_low\":null,");
        return;
    }
    std::vector<std::pair<int, std::pair<unsigned int, unsigned int>>> rows(atTick.begin(), atTick.end());
    const double ticks = tradePrice / sc.TickSize;
    const int tradeTick = static_cast<int>(ticks >= 0.0 ? ticks + 0.5 : ticks - 0.5);
    int stackTick = 0;
    int stackBid = 0;
    int bestDistance = 0;
    bool haveStack = false;
    for (int index = 0; index + 2 < static_cast<int>(rows.size()); ++index)
    {
        if (rows[index + 1].first != rows[index].first + 1) continue;
        if (rows[index + 2].first != rows[index].first + 2) continue;
        bool bidStack = true;
        bool askStack = true;
        for (int step = 0; step < 3; ++step)
        {
            const unsigned int bid = rows[index + step].second.first;
            const unsigned int ask = rows[index + step].second.second;
            if (!(bid > 0 && bid >= ask * 3)) bidStack = false;
            if (!(ask > 0 && ask >= bid * 3)) askStack = false;
        }
        if (!bidStack && !askStack) continue;
        const int tick = rows[index + 1].first;
        const int distance = tick > tradeTick ? tick - tradeTick : tradeTick - tick;
        if (!haveStack || distance < bestDistance)
        {
            haveStack = true;
            bestDistance = distance;
            stackTick = tick;
            stackBid = bidStack ? 1 : 0;
        }
    }
    int unfinishedLowTick = 0;
    int unfinishedHighTick = 0;
    bool unfinishedLow = false;
    bool unfinishedHigh = false;
    bool haveClosed = false;
    for (const auto& item : closedTick)
    {
        const unsigned int bid = item.second.first;
        const unsigned int ask = item.second.second;
        if (bid == 0 && ask == 0) continue;
        if (!haveClosed || item.first < unfinishedLowTick)
        {
            unfinishedLowTick = item.first;
            unfinishedLow = bid > 0 && ask == 0;
        }
        if (!haveClosed || item.first > unfinishedHighTick)
        {
            unfinishedHighTick = item.first;
            unfinishedHigh = ask > 0 && bid == 0;
        }
        haveClosed = true;
    }
    std::fprintf(file, "\"ladder\":[");
    const int count = static_cast<int>(rows.size());
    const int start = count > 800 ? (count - 800) / 2 : 0;
    const int stop = count > 800 ? start + 800 : count;
    for (int index = start; index < stop; ++index)
    {
        if (index > start) std::fprintf(file, ",");
        const double price = rows[index].first * sc.TickSize;
        std::fprintf(file, "{\"p\":%.10g,\"b\":%u,\"a\":%u}", price, rows[index].second.first, rows[index].second.second);
    }
    std::fprintf(file, "],");
    if (haveStack)
        std::fprintf(file, "\"stack\":{\"price\":%.10g,\"side\":\"%s\"},", stackTick * sc.TickSize, stackBid ? "bid" : "ask");
    else
        std::fprintf(file, "\"stack\":null,");
    if (unfinishedHigh)
        std::fprintf(file, "\"unfinished_high\":%.10g,", unfinishedHighTick * sc.TickSize);
    else
        std::fprintf(file, "\"unfinished_high\":null,");
    if (unfinishedLow)
        std::fprintf(file, "\"unfinished_low\":%.10g,", unfinishedLowTick * sc.TickSize);
    else
        std::fprintf(file, "\"unfinished_low\":null,");
}

static double QtyAt(const OrderSnap* rows, int count, int bidSide, double price, double tick)
{
    double qty = 0.0;
    for (int i = 0; i < count; ++i)
    {
        if (rows[i].bid == bidSide && std::fabs(rows[i].price - price) <= tick * 0.51)
            qty += rows[i].qty;
    }
    return qty;
}

static int IceShown(const IceLevel* ice, double now)
{
    return ice != nullptr && ice->active && ice->until >= now && ice->price > 0.0;
}

static bool IceRoot(const char* root)
{
    return std::strcmp(root, "GC") == 0 || std::strcmp(root, "CL") == 0 || std::strcmp(root, "NQ") == 0 || std::strcmp(root, "NG") == 0;
}

static void CollectLevels(SCStudyInterfaceRef sc, int bidSide, int levels, LevelQty* rows, int& count, double tick, double& adjust, int& haveAdjust)
{
    const int kMaxOrders = 16;
    n_ACSIL::s_MarketOrderData orders[kMaxOrders];
    if (levels > 32) levels = 32;
    for (int level = 0; level < levels && count < 64; ++level)
    {
        s_MarketDepthEntry entry;
        if (bidSide) sc.GetBidMarketDepthEntryAtLevel(entry, level);
        else sc.GetAskMarketDepthEntryAtLevel(entry, level);
        if (entry.AdjustedPrice <= 0.0) continue;
        if (!haveAdjust && entry.Price > 0.0)
        {
            adjust = entry.AdjustedPrice - entry.Price;
            haveAdjust = 1;
        }
        double qty = entry.Quantity;
        if (qty <= 0.0)
        {
            int ticks = sc.Round(entry.AdjustedPrice / tick);
            int found = bidSide ? sc.GetBidMarketLimitOrdersForPrice(ticks, kMaxOrders, orders) : sc.GetAskMarketLimitOrdersForPrice(ticks, kMaxOrders, orders);
            for (int i = 0; i < found; ++i) qty += orders[i].OrderQuantity;
        }
        if (qty <= 0.0) continue;
        bool duplicate = false;
        for (int earlier = 0; earlier < count; ++earlier)
        {
            if (rows[earlier].bid == bidSide && std::fabs(rows[earlier].price - entry.AdjustedPrice) <= tick * 0.51)
                duplicate = true;
        }
        if (duplicate) continue;
        rows[count].price = entry.AdjustedPrice;
        rows[count].qty = qty;
        rows[count].bid = bidSide;
        ++count;
    }
}

static void WatchIcebergs(SCStudyInterfaceRef sc, MboState* state, IceBook* book, const char* root, double tradePrice, double tick, double now)
{
    state->bidIce.active = 0;
    state->askIce.active = 0;
    state->primaryBid = -1;
    book->shown = 0;
    if (!IceRoot(root) || tick <= 0.0)
    {
        book->count = 0;
        state->icebergUntil = 0.0;
        return;
    }
    const char* symbol = sc.Symbol.GetChars();
    double floorQty = std::strcmp(root, "NQ") == 0 ? 30.0 : 10.0;
    if (std::strstr(symbol, "MNQ") != nullptr) floorQty = 300.0;
    else if (std::strstr(symbol, "MGC") != nullptr) floorQty = 100.0;
    else if (std::strstr(symbol, "MCL") != nullptr) floorQty = 100.0;
    LevelQty levels[64];
    int levelCount = 0;
    double adjust = 0.0;
    int haveAdjust = 0;
    CollectLevels(sc, 1, sc.GetBidMarketDepthNumberOfLevels(), levels, levelCount, tick, adjust, haveAdjust);
    CollectLevels(sc, 0, sc.GetAskMarketDepthNumberOfLevels(), levels, levelCount, tick, adjust, haveAdjust);
    if (!book->ready)
    {
        book->ready = 1;
        book->lastSales = sc.CurrentSystemDateTime.GetAsDouble();
        book->count = 0;
        for (int i = 0; i < levelCount && book->count < 64; ++i)
        {
            IceWatch& row = book->row[book->count++];
            row.price = levels[i].price;
            row.qty = levels[i].qty;
            row.refilled = 0.0;
            row.bid = levels[i].bid;
            row.active = 0;
        }
        state->icebergUntil = 0.0;
        return;
    }
    double traded[64];
    for (int i = 0; i < 64; ++i) traded[i] = 0.0;
    c_SCTimeAndSalesArray sales;
    sc.GetTimeAndSales(sales);
    double newest = book->lastSales;
    for (int index = sales.Size() - 1; index >= 0; --index)
    {
        const s_TimeAndSales& trade = sales[index];
        if (trade.Volume <= 0) continue;
        const double when = trade.DateTime.GetAsDouble();
        if (when <= book->lastSales) break;
        if (when > newest) newest = when;
        const int bidSide = trade.Type == SC_TS_BID ? 1 : trade.Type == SC_TS_ASK ? 0 : -1;
        if (bidSide < 0) continue;
        const double price = trade.Price + adjust;
        for (int i = 0; i < levelCount; ++i)
        {
            if (levels[i].bid != bidSide) continue;
            if (std::fabs(levels[i].price - price) <= tick * 0.51) traded[i] += trade.Volume;
        }
    }
    book->lastSales = newest;
    IceWatch next[64];
    int nextCount = 0;
    for (int i = 0; i < levelCount && nextCount < 64; ++i)
    {
        if (levels[i].qty <= 0.0) continue;
        int found = -1;
        for (int w = 0; w < book->count; ++w)
        {
            if (book->row[w].bid == levels[i].bid && std::fabs(book->row[w].price - levels[i].price) <= tick * 0.51)
            {
                found = w;
                break;
            }
        }
        IceWatch row = {};
        row.price = levels[i].price;
        row.qty = levels[i].qty;
        row.bid = levels[i].bid;
        if (found >= 0)
        {
            const IceWatch& prev = book->row[found];
            row.refilled = prev.refilled;
            row.active = prev.active;
            if (prev.qty >= floorQty)
            {
                double drop = prev.qty - levels[i].qty;
                if (drop < 0.0) drop = 0.0;
                const double added = traded[i] - drop;
                if (added > 0.0) row.refilled += added;
            }
            if (row.refilled >= floorQty) row.active = 1;
        }
        next[nextCount++] = row;
    }
    book->count = nextCount;
    for (int i = 0; i < nextCount; ++i) book->row[i] = next[i];
    int order[64];
    int activeCount = 0;
    for (int i = 0; i < book->count; ++i)
    {
        if (book->row[i].active && book->row[i].qty > 0.0) order[activeCount++] = i;
    }
    for (int i = 0; i < activeCount; ++i)
    {
        for (int j = i + 1; j < activeCount; ++j)
        {
            const double left = std::fabs(book->row[order[i]].price - tradePrice);
            const double right = std::fabs(book->row[order[j]].price - tradePrice);
            if (right < left)
            {
                const int swap = order[i];
                order[i] = order[j];
                order[j] = swap;
            }
        }
    }
    book->shown = activeCount > 8 ? 8 : activeCount;
    for (int i = 0; i < book->shown; ++i)
    {
        const IceWatch& row = book->row[order[i]];
        book->out[i].price = row.price;
        book->out[i].qty = row.qty;
        book->out[i].refilled = row.refilled;
        book->out[i].bid = row.bid;
    }
    int bestBid = -1;
    int bestAsk = -1;
    for (int i = 0; i < book->shown; ++i)
    {
        if (book->out[i].bid && bestBid < 0) bestBid = i;
        if (!book->out[i].bid && bestAsk < 0) bestAsk = i;
    }
    if (bestBid >= 0)
    {
        state->bidIce.active = 1;
        state->bidIce.price = book->out[bestBid].price;
        state->bidIce.bid = 1;
        state->bidIce.refills = book->out[bestBid].refilled >= 1.0 ? static_cast<int>(book->out[bestBid].refilled) : 1;
        state->bidIce.until = now + 86400.0;
    }
    if (bestAsk >= 0)
    {
        state->askIce.active = 1;
        state->askIce.price = book->out[bestAsk].price;
        state->askIce.bid = 0;
        state->askIce.refills = book->out[bestAsk].refilled >= 1.0 ? static_cast<int>(book->out[bestAsk].refilled) : 1;
        state->askIce.until = now + 86400.0;
    }
    const bool bidNear = bestBid >= 0 && (bestAsk < 0 || std::fabs(book->out[bestBid].price - tradePrice) <= std::fabs(book->out[bestAsk].price - tradePrice));
    if (bestBid >= 0 || bestAsk >= 0)
    {
        state->primaryBid = bidNear ? 1 : 0;
        state->icebergUntil = now + 86400.0;
    }
    else
        state->icebergUntil = 0.0;
}

static void CollectSide(SCStudyInterfaceRef sc, int bidSide, int levels, OrderSnap* rows, int& count)
{
    const int kMaxOrders = 16;
    n_ACSIL::s_MarketOrderData orders[kMaxOrders];
    if (levels > 32) levels = 32;
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
        sc.StudyDescription = "Writes the session point of control, value area, and the iceberg price. Does not trade.";
        sc.AutoLoop = 0;
        sc.MaintainVolumeAtPriceData = 1;
        sc.UsesMarketDepthData = 1;
        sc.UpdateAlways = 1;
        sc.FreeDLL = 0;
        return;
    }
    char root[8] = {};
    if (!RootFromSymbol(sc.Symbol, root, sizeof root)) return;
    MboState* state = static_cast<MboState*>(sc.GetPersistentPointer(3));
    if (state == nullptr)
    {
        state = static_cast<MboState*>(sc.AllocateMemory(sizeof(MboState)));
        if (state == nullptr) return;
        std::memset(state, 0, sizeof(MboState));
        state->primaryBid = -1;
        sc.SetPersistentPointer(3, state);
    }
    IceBook* iceBook = static_cast<IceBook*>(sc.GetPersistentPointer(4));
    if (iceBook == nullptr)
    {
        iceBook = static_cast<IceBook*>(sc.AllocateMemory(sizeof(IceBook)));
        if (iceBook == nullptr) return;
        std::memset(iceBook, 0, sizeof(IceBook));
        sc.SetPersistentPointer(4, iceBook);
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
        }
    }
    WatchIcebergs(sc, state, iceBook, root, tradePrice, tick, now);
    state->prevCount = count;
    if (count > 0) std::memcpy(state->prev, current, sizeof(OrderSnap) * static_cast<size_t>(count));
    SCString path;
    path.Format("%szeus_mbo_%s.json", sc.DataFilesFolder().GetChars(), root);
    FILE* file = std::fopen(path.GetChars(), "wb");
    if (file == nullptr) return;
    const ValueArea area = SessionValue(sc);
    double delta5 = 0.0;
    double delta60 = 0.0;
    TradeDelta(sc, delta5, delta60);
    const IceLevel* primary = nullptr;
    const IceLevel* other = nullptr;
    if (state->primaryBid == 1) { primary = &state->bidIce; other = &state->askIce; }
    else if (state->primaryBid == 0) { primary = &state->askIce; other = &state->bidIce; }
    std::fprintf(file, "{\"source\":\"SIERRA_ACSIL_MBO\",\"symbol\":\"%s\",\"sweep_consumed\":%d,\"iceberg_refresh\":%d,\"size_pulled\":%d,", root, state->sweepUntil >= now ? 1 : 0, state->icebergUntil >= now ? 1 : 0, state->pulledUntil >= now ? 1 : 0);
    if (IceShown(primary, now))
        std::fprintf(file, "\"iceberg\":{\"price\":%.10g,\"side\":\"%s\",\"refills\":%d,\"time\":%.0f},", primary->price, primary->bid ? "bid" : "ask", primary->refills, primary->until);
    else
        std::fprintf(file, "\"iceberg\":null,");
    if (IceShown(other, now))
        std::fprintf(file, "\"other\":{\"price\":%.10g,\"side\":\"%s\",\"refills\":%d,\"time\":%.0f},", other->price, other->bid ? "bid" : "ask", other->refills, other->until);
    else
        std::fprintf(file, "\"other\":null,");
    if (sc.Bid > 0.0 && sc.Ask > 0.0)
        std::fprintf(file, "\"bid\":%.10g,\"ask\":%.10g,", sc.Bid, sc.Ask);
    else
        std::fprintf(file, "\"bid\":null,\"ask\":null,");
    std::fprintf(file, "\"icebergs\":[");
    for (int i = 0; i < iceBook->shown; ++i)
    {
        if (i > 0) std::fprintf(file, ",");
        std::fprintf(file, "{\"price\":%.10g,\"side\":\"%s\",\"shown\":%.10g}", iceBook->out[i].price, iceBook->out[i].bid ? "BUY" : "SELL", iceBook->out[i].qty);
    }
    std::fprintf(file, "],");
    WriteMarks(file, sc, root, tradePrice);
    if (area.have)
        std::fprintf(file, "\"poc\":%.10g,\"vah\":%.10g,\"val\":%.10g,\"last\":%.10g,\"delta_5s\":%.10g,\"delta_60s\":%.10g}\n", area.poc, area.vah, area.val, tradePrice, delta5, delta60);
    else
        std::fprintf(file, "\"poc\":null,\"vah\":null,\"val\":null,\"last\":%.10g,\"delta_5s\":%.10g,\"delta_60s\":%.10g}\n", tradePrice, delta5, delta60);
    std::fclose(file);
}

export default async function handler(req, res) {
  // 支持 GET 和 POST 请求
  if (req.method === 'GET') {
    // GET 请求返回看板数据
    try {
      // 从每日数据表获取最新记录
      const dashboardData = await fetchLatestDailyData();
      return res.status(200).json(dashboardData);
      
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
      return res.status(500).json({ 
        error: 'Internal server error',
        message: error.message 
      });
    }
  }
  
  if (req.method === 'POST') {
    // POST 请求触发 GitHub Actions 计算收益数据
    try {
      const { mode = 'profit' } = req.body;
      
      // 验证参数
      const validModes = ['profit'];
      if (!validModes.includes(mode)) {
        return res.status(400).json({ 
          error: 'Invalid mode. Must be one of: profit' 
        });
      }

      // 调用 GitHub API 触发 Actions
      const response = await fetch(
        `https://api.github.com/repos/YiZhiYuanYuan-qyy/fund_daily_view/actions/workflows/run-daily-view.yml/dispatches`,
        {
          method: 'POST',
          headers: {
            'Authorization': `token ${process.env.GITHUB_TOKEN}`,
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Vercel-Trigger-DailyView'
          },
          body: JSON.stringify({
            ref: 'main',
            inputs: {
              mode: mode
            }
          })
        }
      );

      if (!response.ok) {
        const errorText = await response.text();
        console.error('GitHub API error:', response.status, errorText);
        return res.status(response.status).json({ 
          error: 'Failed to trigger GitHub Actions',
          details: errorText
        });
      }

      console.log(`Successfully triggered daily view calculation with mode: ${mode}`);
      
      return res.status(200).json({
        success: true,
        message: 'Daily view calculation triggered successfully',
        mode: mode,
        timestamp: new Date().toISOString()
      });

    } catch (error) {
      console.error('Error triggering daily view calculation:', error);
      return res.status(500).json({ 
        error: 'Internal server error',
        message: error.message 
      });
    }
  }
  
  return res.status(405).json({ error: 'Method not allowed. Use GET or POST.' });
}

// 从每日数据表获取最新记录
async function fetchLatestDailyData() {
  const NOTION_TOKEN = process.env.NOTION_TOKEN;
  const DAILY_DATA_DB_ID = process.env.DAILY_DATA_DB_ID;
  
  if (!NOTION_TOKEN || !DAILY_DATA_DB_ID) {
    console.log('Missing NOTION_TOKEN or DAILY_DATA_DB_ID, returning mock data');
    return {
      dailyProfit: 0,
      holdingProfit: 0,
      totalProfit: 0,
      totalCost: 0,
      updateTime: new Date().toLocaleString('zh-CN')
    };
  }

  try {
    // 查询最新的记录（按创建时间排序）
    const response = await fetch(`https://api.notion.com/v1/databases/${DAILY_DATA_DB_ID}/query`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${NOTION_TOKEN}`,
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        sorts: [
          {
            timestamp: 'created_time',
            direction: 'descending'
          }
        ],
        page_size: 1
      })
    });

    if (!response.ok) {
      throw new Error(`Notion API error: ${response.status}`);
    }

    const data = await response.json();
    const results = data.results || [];

    if (results.length === 0) {
      console.log('No records found in daily data table, fetching current holdings data');
      const holdingProfit = await fetchCurrentHoldingProfit();
      return {
        dailyProfit: 0,
        holdingProfit: holdingProfit,
        totalProfit: 0,
        totalCost: 0,
        updateTime: new Date().toLocaleString('zh-CN')
      };
    }

    const record = results[0];
    const properties = record.properties || {};

    // 提取数据
    const dailyProfit = getNumberValue(properties['当日收益']) || 0;
    const totalCost = getNumberValue(properties['持仓成本']) || 0;
    const totalProfit = getNumberValue(properties['总收益']) || 0;
    
    // 从持仓表获取真实的持有收益
    const holdingProfit = await fetchCurrentHoldingProfit();

    // 获取记录的创建时间或日期字段
    const updateTime = record.created_time ? 
      new Date(record.created_time).toLocaleString('zh-CN') :
      new Date().toLocaleString('zh-CN');

    return {
      dailyProfit: Number(dailyProfit.toFixed(2)),
      holdingProfit: Number(holdingProfit.toFixed(2)),
      totalProfit: Number(totalProfit.toFixed(2)),
      totalCost: Number(totalCost.toFixed(2)),
      updateTime: updateTime
    };

  } catch (error) {
    console.error('Error fetching from Notion:', error);
    // 尝试至少获取持有收益
    try {
      const holdingProfit = await fetchCurrentHoldingProfit();
      return {
        dailyProfit: 0,
        holdingProfit: holdingProfit,
        totalProfit: 0,
        totalCost: 0,
        updateTime: new Date().toLocaleString('zh-CN')
      };
    } catch (holdingError) {
      console.error('Error fetching holding profit as fallback:', holdingError);
      return {
        dailyProfit: 0,
        holdingProfit: 0,
        totalProfit: 0,
        totalCost: 0,
        updateTime: new Date().toLocaleString('zh-CN')
      };
    }
  }
}

// 从持仓表获取当前持有收益
async function fetchCurrentHoldingProfit() {
  const NOTION_TOKEN = process.env.NOTION_TOKEN;
  const HOLDINGS_DB_ID = process.env.HOLDINGS_DB_ID;
  
  if (!NOTION_TOKEN || !HOLDINGS_DB_ID) {
    console.log('Missing NOTION_TOKEN or HOLDINGS_DB_ID for holdings data');
    return 0;
  }

  try {
    let totalHoldingProfit = 0;
    let cursor = null;
    
    do {
      const payload = {
        page_size: 100
      };
      
      if (cursor) {
        payload.start_cursor = cursor;
      }

      const response = await fetch(`https://api.notion.com/v1/databases/${HOLDINGS_DB_ID}/query`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${NOTION_TOKEN}`,
          'Notion-Version': '2022-06-28',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error(`Holdings API error: ${response.status}`);
      }

      const data = await response.json();
      const results = data.results || [];

      for (const holding of results) {
        const properties = holding.properties || {};
        
        // 检查持仓份额是否大于0
        const quantity = getNumberValue(properties['持仓份额']) || 0;
        
        if (quantity > 0) {
          // 获取持有收益
          const holdingProfit = getNumberValue(properties['持有收益']) || 0;
          totalHoldingProfit += holdingProfit;
        }
      }

      cursor = data.next_cursor;
    } while (cursor);

    return Number(totalHoldingProfit.toFixed(2));

  } catch (error) {
    console.error('Error fetching holding profit:', error);
    return 0;
  }
}

// 提取 Notion 数字属性值
function getNumberValue(property) {
  if (!property) return null;
  
  switch (property.type) {
    case 'number':
      return property.number;
    case 'formula':
      return property.formula?.number;
    case 'rollup':
      return property.rollup?.number;
    default:
      return null;
  }
}

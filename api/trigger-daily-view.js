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
    // 获取当天日期，格式为 @YYYY-MM-DD
    const today = new Date();
    const todayStr = `@${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    
    // 查询当天的记录
    const response = await fetch(`https://api.notion.com/v1/databases/${DAILY_DATA_DB_ID}/query`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${NOTION_TOKEN}`,
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        filter: {
          property: '日期',
          title: {
            equals: todayStr
          }
        },
        page_size: 1
      })
    });

    if (!response.ok) {
      throw new Error(`Notion API error: ${response.status}`);
    }

    const data = await response.json();
    const results = data.results || [];

    if (results.length === 0) {
      console.log(`No record found for today (${todayStr}), fetching current holdings data`);
      const { holdingProfit, currentDailyProfit } = await fetchCurrentHoldingsData();
      
      // 如果没有找到当天记录，尝试创建一条新记录
      if (currentDailyProfit !== 0) {
        console.log(`Creating new daily data record for today with 当日收益: ${currentDailyProfit}`);
        await createDailyDataRecord(todayStr, currentDailyProfit, 0, 0);
      }
      
      return {
        dailyProfit: currentDailyProfit,
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
    
    // 从持仓表获取真实的持有收益和当日收益
    const { holdingProfit, currentDailyProfit } = await fetchCurrentHoldingsData();
    
    // 优先使用持仓表的实时数据
    const finalDailyProfit = currentDailyProfit !== 0 ? currentDailyProfit : dailyProfit;

    // 如果持仓表的当日收益与每日数据表不一致，则更新每日数据表
    if (Math.abs(finalDailyProfit - dailyProfit) > 0.01) {
      console.log(`Updating daily data table: 持仓表当日收益(${finalDailyProfit}) vs 每日数据表(${dailyProfit})`);
      await updateDailyDataTable(record.id, finalDailyProfit, totalCost, totalProfit);
    }

    // 获取记录的创建时间或日期字段
    const updateTime = record.created_time ? 
      new Date(record.created_time).toLocaleString('zh-CN') :
      new Date().toLocaleString('zh-CN');

    return {
      dailyProfit: Number(finalDailyProfit.toFixed(2)),
      holdingProfit: Number(holdingProfit.toFixed(2)),
      totalProfit: Number(totalProfit.toFixed(2)),
      totalCost: Number(totalCost.toFixed(2)),
      updateTime: updateTime
    };

  } catch (error) {
    console.error('Error fetching from Notion:', error);
    // 尝试至少获取持仓数据
    try {
      const { holdingProfit, currentDailyProfit } = await fetchCurrentHoldingsData();
      return {
        dailyProfit: currentDailyProfit,
        holdingProfit: holdingProfit,
        totalProfit: 0,
        totalCost: 0,
        updateTime: new Date().toLocaleString('zh-CN')
      };
    } catch (holdingError) {
      console.error('Error fetching holdings data as fallback:', holdingError);
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

// 创建每日数据记录
async function createDailyDataRecord(dateStr, dailyProfit, totalCost, totalProfit) {
  const NOTION_TOKEN = process.env.NOTION_TOKEN;
  const DAILY_DATA_DB_ID = process.env.DAILY_DATA_DB_ID;
  
  if (!NOTION_TOKEN || !DAILY_DATA_DB_ID) {
    console.log('Missing NOTION_TOKEN or DAILY_DATA_DB_ID, cannot create daily data record');
    return false;
  }

  try {
    const response = await fetch(`https://api.notion.com/v1/pages`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${NOTION_TOKEN}`,
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        parent: {
          database_id: DAILY_DATA_DB_ID
        },
        properties: {
          '日期': {
            title: [
              {
                text: {
                  content: dateStr
                }
              }
            ]
          },
          '当日收益': {
            number: dailyProfit
          },
          '持仓成本': {
            number: totalCost
          },
          '总收益': {
            number: totalProfit
          }
        }
      })
    });

    if (response.ok) {
      console.log(`Successfully created daily data record for ${dateStr} with 当日收益: ${dailyProfit}`);
      return true;
    } else {
      console.error(`Failed to create daily data record: ${response.status}`);
      return false;
    }
  } catch (error) {
    console.error('Error creating daily data record:', error);
    return false;
  }
}

// 更新每日数据表
async function updateDailyDataTable(pageId, dailyProfit, totalCost, totalProfit) {
  const NOTION_TOKEN = process.env.NOTION_TOKEN;
  
  if (!NOTION_TOKEN) {
    console.log('Missing NOTION_TOKEN, cannot update daily data table');
    return false;
  }

  try {
    const response = await fetch(`https://api.notion.com/v1/pages/${pageId}`, {
      method: 'PATCH',
      headers: {
        'Authorization': `Bearer ${NOTION_TOKEN}`,
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        properties: {
          '当日收益': {
            number: dailyProfit
          }
        }
      })
    });

    if (response.ok) {
      console.log(`Successfully updated daily data table with 当日收益: ${dailyProfit}`);
      return true;
    } else {
      console.error(`Failed to update daily data table: ${response.status}`);
      return false;
    }
  } catch (error) {
    console.error('Error updating daily data table:', error);
    return false;
  }
}

// 从持仓表获取当前持有收益和当日收益
async function fetchCurrentHoldingsData() {
  const NOTION_TOKEN = process.env.NOTION_TOKEN;
  const HOLDINGS_DB_ID = process.env.HOLDINGS_DB_ID;
  
  if (!NOTION_TOKEN || !HOLDINGS_DB_ID) {
    console.log('Missing NOTION_TOKEN or HOLDINGS_DB_ID for holdings data');
    return { holdingProfit: 0, currentDailyProfit: 0 };
  }

  try {
    let totalHoldingProfit = 0;
    let totalDailyProfit = 0;
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
          
          // 获取当日收益
          const dailyProfit = getNumberValue(properties['当日收益']) || 0;
          totalDailyProfit += dailyProfit;
        }
      }

      cursor = data.next_cursor;
    } while (cursor);

    return {
      holdingProfit: Number(totalHoldingProfit.toFixed(2)),
      currentDailyProfit: Number(totalDailyProfit.toFixed(2))
    };

  } catch (error) {
    console.error('Error fetching holdings data:', error);
    return { holdingProfit: 0, currentDailyProfit: 0 };
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

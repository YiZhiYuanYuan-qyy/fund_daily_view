export default async function handler(req, res) {
  // 支持 GET 和 POST 请求
  if (req.method === 'GET') {
    // GET 请求返回看板数据
    try {
      // 这里应该从 Notion 数据库获取计算好的数据
      // 暂时返回模拟数据，后续需要连接到您的 Notion 数据库
      const dashboardData = {
        dailyProfit: 123.45,
        holdingProfit: 1234.56,
        totalProfit: 1357.01,
        totalCost: 50000.00,
        updateTime: new Date().toLocaleString('zh-CN')
      };
      
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

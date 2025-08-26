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
    // POST 请求触发数据更新（当 fund-sync 更新时调用）
    try {
      // 这里可以触发重新计算或者直接返回成功
      // 实际应用中，这个接口会被 fund-sync 的 webhook 调用
      
      return res.status(200).json({
        success: true,
        message: 'Dashboard data updated successfully',
        timestamp: new Date().toISOString()
      });

    } catch (error) {
      console.error('Error updating dashboard data:', error);
      return res.status(500).json({ 
        error: 'Internal server error',
        message: error.message 
      });
    }
  }
  
  return res.status(405).json({ error: 'Method not allowed. Use GET or POST.' });
}
